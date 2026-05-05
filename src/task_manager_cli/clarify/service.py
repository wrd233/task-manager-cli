import json
from typing import Any, Dict, List, Optional

from task_manager_cli.config.settings import Settings
from task_manager_cli.core.enums import ProposalStatus
from task_manager_cli.core.errors import ConfigError, NotFoundError, TaskManagerError
from task_manager_cli.privacy.redactor import Redactor
from task_manager_cli.proposals.service import ProposalService, classify_risk
from task_manager_cli.providers.base import (
    DryRunProvider,
    ProviderConfigError,
    ProviderError,
    ProviderResponseError,
    provider_from_settings,
)
from task_manager_cli.reviews.service import ReviewSessionService
from task_manager_cli.storage.repositories import Repository


BASIC_QUESTIONS = [
    {"id": "value", "text": "这个条目现在还有价值吗？"},
    {"id": "classification", "text": "它更像：行动 / 想法 / 资源 / 等待 / 未来可能 / 已完成 / 丢弃？"},
    {"id": "project", "text": "它是否属于某个项目？"},
    {"id": "mini_project", "text": "它是否需要拆成小任务？"},
    {"id": "waiting", "text": "它是否需要等待别人或外部条件？"},
    {"id": "result", "text": "它完成后是否需要成果标注？"},
    {"id": "handling", "text": "你希望如何处理它？"},
]


class ClarifyService:
    def __init__(self, conn, settings: Settings):
        self.conn = conn
        self.settings = settings
        self.repo = Repository(conn)
        self.reviews = ReviewSessionService(conn)
        self.proposals = ProposalService(conn, settings)
        self.redactor = Redactor(settings.sensitive_patterns)

    def start_selected(
        self,
        ids: List[str],
        answer: Optional[str] = None,
        skip_reason: Optional[str] = None,
        provider_name: str = "mock",
        title: Optional[str] = None,
        dry_run_preview: bool = False,
    ) -> Dict[str, Any]:
        if not ids:
            raise ValueError("clarify selected requires at least one id.")
        review_id = self.reviews.start("clarify:selected", item_refs=ids, title=title or "Clarify selected")
        return self.run_review(review_id, answer=answer, skip_reason=skip_reason, provider_name=provider_name, dry_run_preview=dry_run_preview)

    def start_inbox(self, limit: int = 10, **kwargs) -> Dict[str, Any]:
        ids = self.inbox_candidates(limit=limit)
        if not ids:
            review_id = self.reviews.start("clarify:inbox", item_refs=[], title="Clarify inbox")
            return {"review_id": review_id, "items": [], "proposals": [], "table": "No inbox clarify candidates found."}
        review_id = self.reviews.start("clarify:inbox", item_refs=ids, title="Clarify inbox")
        return self.run_review(review_id, **kwargs)

    def start_today(self, limit: int = 10, **kwargs) -> Dict[str, Any]:
        ids = self.today_candidates(limit=limit)
        review_id = self.reviews.start("clarify:today", item_refs=ids, title="Clarify today")
        return self.run_review(review_id, **kwargs)

    def start_project(self, project_ref: str, limit: int = 10, **kwargs) -> Dict[str, Any]:
        ids = self.project_candidates(project_ref, limit=limit)
        review_id = self.reviews.start("clarify:project", item_refs=ids, title=f"Clarify project {project_ref}")
        return self.run_review(review_id, **kwargs)

    def resume(self, review_id: int, **kwargs) -> Dict[str, Any]:
        self.reviews.set_status(review_id, "in_progress")
        return self.run_review(review_id, **kwargs)

    def run_review(
        self,
        review_id: int,
        answer: Optional[str] = None,
        skip_reason: Optional[str] = None,
        provider_name: str = "mock",
        dry_run_preview: bool = False,
    ) -> Dict[str, Any]:
        provider = provider_from_settings(self.settings, override_name=provider_name)
        self.reviews.set_status(review_id, "in_progress")
        processed: List[Dict[str, Any]] = []
        previews: List[Dict[str, Any]] = []
        generated: List[int] = []
        for item in self.reviews.pending_clarify_items(review_id):
            object_id = item.get("object_id")
            if not object_id:
                self.reviews.update_item_clarify(item["id"], {"status": "failed", "error": "Only object clarify is supported in this round."})
                continue
            obj = self.repo.get_object(int(object_id))
            if not obj:
                raise NotFoundError(f"Clarify object not found: {object_id}")
            if skip_reason is not None:
                self._mark_asked(item["id"])
                self.reviews.skip_item(item["id"], skip_reason)
                processed.append({"review_item_id": item["id"], "status": "skipped"})
                continue
            item_answer = answer
            if item_answer is None:
                item_answer = self._prompt_answer(obj)
            self._record_questions_and_answer(item["id"], item_answer)
            payload = self.build_payload(review_id, item["id"], obj, item_answer)
            if dry_run_preview or isinstance(provider, DryRunProvider):
                preview = provider.preview_payload(payload)
                previews.append(preview)
                self.reviews.update_item_clarify(
                    item["id"],
                    {
                        "status": "submitted",
                        "provider": provider.config.name,
                        "provider_request_summary": self._payload_summary(preview),
                        "provider_response_summary": {"dry_run": True},
                    },
                )
                processed.append({"review_item_id": item["id"], "status": "submitted", "dry_run": True})
                continue
            try:
                result = provider.generate(payload)
            except (ProviderConfigError, ProviderError, ProviderResponseError) as exc:
                self.reviews.update_item_clarify(item["id"], {"status": "failed", "provider": provider.config.name, "error": str(exc)})
                processed.append({"review_item_id": item["id"], "status": "failed", "error": str(exc)})
                continue
            proposal_ids = self._result_to_proposals(review_id, int(object_id), result)
            generated.extend(proposal_ids)
            self.reviews.update_item_clarify(
                item["id"],
                {
                    "status": "proposal_generated" if proposal_ids else "submitted",
                    "provider": provider.config.name,
                    "provider_request_summary": self._payload_summary(payload),
                    "provider_response_summary": {
                        "summary": result.summary,
                        "candidate_count": len(result.proposal_candidates),
                        "confidence": result.confidence,
                        "reasoning_summary": result.reasoning_summary,
                    },
                    "generated_proposal_ids": proposal_ids,
                },
            )
            processed.append({"review_item_id": item["id"], "status": "proposal_generated", "proposal_ids": proposal_ids})
        proposals = self.proposals.list(review_session_id=review_id, limit=200)
        return {
            "review_id": review_id,
            "items": processed,
            "payload_previews": previews,
            "proposals": proposals,
            "table": proposal_table(proposals, self.repo),
        }

    def build_payload(self, review_id: int, review_item_id: int, obj: Dict[str, Any], answer: str) -> Dict[str, Any]:
        raw = {
            "prompt_version": self.settings.provider_prompt_version,
            "review_id": review_id,
            "review_item_id": review_item_id,
            "item": {
                "id": obj.get("id"),
                "type": obj.get("object_type"),
                "title": obj.get("title"),
                "status": obj.get("status"),
                "metadata": {
                    "priority": obj.get("metadata", {}).get("priority"),
                    "semantic_tags": obj.get("metadata", {}).get("semantic_tags"),
                    "semantic_marker": obj.get("metadata", {}).get("semantic_marker"),
                },
                "location": {
                    "page_name": obj.get("page_name"),
                    "journal_date": obj.get("journal_date"),
                    "line_start": obj.get("line_start"),
                    "block_uuid_present": bool(obj.get("block_uuid")),
                },
            },
            "questions": BASIC_QUESTIONS,
            "answers": [{"question_id": "freeform", "answer": answer}],
            "constraints": [
                "Provider output can only become suggested Proposal.",
                "Do not directly modify facts.",
                "Do not write Logseq.",
                "Return JSON only.",
            ],
        }
        return redact_json(raw, self.redactor)

    def inbox_candidates(self, limit: int = 10) -> List[str]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT o.id
            FROM objects o
            LEFT JOIN object_record_links orl ON orl.object_id=o.id
            LEFT JOIN source_records r ON r.id=orl.record_id
            WHERE o.object_type IN ('task', 'idea')
              AND (
                r.metadata_json LIKE '%inbox%'
                OR r.metadata_json LIKE '%待澄清%'
                OR o.status IN ('todo', 'waiting', 'captured')
              )
            ORDER BY o.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [str(row["id"]) for row in rows]

    def today_candidates(self, limit: int = 10) -> List[str]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT o.id
            FROM objects o
            LEFT JOIN locations l ON l.id=o.canonical_location_id
            WHERE o.object_type IN ('task', 'idea') AND l.journal_date IS NOT NULL
            ORDER BY l.journal_date DESC, o.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [str(row["id"]) for row in rows]

    def project_candidates(self, project_ref: str, limit: int = 10) -> List[str]:
        project_id = self.repo.resolve_object_id(project_ref)
        if project_id is None:
            raise NotFoundError(f"Project not found: {project_ref}")
        rows = self.conn.execute(
            """
            SELECT DISTINCT o.id
            FROM relations rel
            JOIN objects o ON o.id=rel.from_object_id
            WHERE rel.to_object_id=? AND rel.relation_type='belongs_to'
              AND o.object_type IN ('task', 'idea')
            ORDER BY o.id DESC
            LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
        return [str(row["id"]) for row in rows]

    def _mark_asked(self, review_item_id: int) -> None:
        self.reviews.update_item_clarify(review_item_id, {"status": "asked", "questions": BASIC_QUESTIONS})

    def _record_questions_and_answer(self, review_item_id: int, answer: str) -> None:
        self.reviews.update_item_clarify(review_item_id, {"status": "asked", "questions": BASIC_QUESTIONS})
        self.reviews.record_answer(review_item_id, "freeform", "Clarify freeform answer", answer)

    def _result_to_proposals(self, review_id: int, object_id: int, result) -> List[int]:
        proposal_ids: List[int] = []
        for candidate in result.proposal_candidates:
            proposal_type = candidate["proposal_type"]
            payload = dict(candidate.get("payload") or {})
            if proposal_type == "logseq_append_marker" and "marker" not in payload:
                payload["marker"] = "**[AI注]**"
            risk = candidate.get("risk") or classify_risk(proposal_type, payload)
            proposal_id = self.proposals.create(
                proposal_type,
                candidate.get("title") or result.summary or "Provider proposal",
                payload,
                risk=risk,
                target_object_ref=str(object_id),
                review_session_id=review_id,
                source="provider",
                rationale=candidate.get("reasoning_summary") or result.reasoning_summary,
                metadata={
                    "provider_confidence": candidate.get("confidence", result.confidence),
                    "provider_summary": result.summary,
                    "needs_user_confirmation": result.needs_user_confirmation,
                },
            )
            proposal_ids.append(proposal_id)
            self.reviews.attach_proposal(review_id, proposal_id, actor="provider")
        return proposal_ids

    def _payload_summary(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"keys": sorted(payload.keys()), "size_chars": len(json.dumps(payload, ensure_ascii=False))}

    def _prompt_answer(self, obj: Dict[str, Any]) -> str:
        print(f"\nClarify item #{obj.get('id')}: {obj.get('title')}")
        print(f"status: {obj.get('status') or ''} | page: {obj.get('page_name') or ''}:{obj.get('line_start') or ''}")
        for index, question in enumerate(BASIC_QUESTIONS, 1):
            print(f"{index}. {question['text']}")
        answer = input("回答，或输入 skip / quit: ").strip()
        if answer == "quit":
            raise TaskManagerError("Clarify quit by user.")
        if answer == "skip":
            return ""
        return answer


def redact_json(data: Any, redactor: Redactor) -> Any:
    if isinstance(data, dict):
        return {key: redact_json(value, redactor) for key, value in data.items()}
    if isinstance(data, list):
        return [redact_json(value, redactor) for value in data]
    if isinstance(data, str):
        return redactor.redact(data).text
    return data


def proposal_table(proposals: List[Dict[str, Any]], repo: Repository) -> str:
    if not proposals:
        return "No proposals generated."
    headers = ["ID", "条目", "当前状态", "Provider 建议", "风险", "置信度", "操作"]
    rows: List[List[str]] = []
    for proposal in proposals:
        obj = repo.get_object(int(proposal["target_object_id"])) if proposal.get("target_object_id") else None
        confidence = proposal.get("metadata", {}).get("provider_confidence")
        rows.append(
            [
                str(proposal.get("id")),
                str((obj or {}).get("title") or proposal.get("target_object_id") or ""),
                str((obj or {}).get("status") or ""),
                str(proposal.get("title") or "")[:48],
                str(proposal.get("risk") or ""),
                "" if confidence is None else str(confidence),
                "accept / reject / edit / apply",
            ]
        )
    widths = [len(item) for item in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def line(values: List[str]) -> str:
        return " | ".join(values[index].ljust(widths[index]) for index in range(len(values)))

    sep = " | ".join("-" * width for width in widths)
    return "\n".join([line(headers), sep] + [line(row) for row in rows])
