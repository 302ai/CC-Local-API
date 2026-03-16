from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query
from app.api.response import ok
from pydantic import BaseModel


from app.db.session import get_db, run_in_threadpool
from app.core.oc_ops import oc_list_exec_session_ids_from_sessions_json, oc_session_id_to_openai_messages, \
    read_jsonl_as_list
from app.repositories.job_session_agent_repo import JobSessionAgentRepository
from app.repositories.job_sync_log_repo import JobSyncLogRepository


router = APIRouter()


class CronRunItem(BaseModel):
    job_id: str
    ts: int


class PushCronRunsPayload(BaseModel):
    items: list[CronRunItem]


def get_job_session_agent_repo(db=Depends(get_db)) -> JobSessionAgentRepository:
    return JobSessionAgentRepository(db)


def get_job_sync_log_repo(db=Depends(get_db)) -> JobSyncLogRepository:
    return JobSyncLogRepository(db)


@router.get("/cron/get_messages")
async def get_all_cron_sessions_messages_v2():
    """
    获取所有定时任务的消息记录（优化版）
    返回统一格式，每条记录都包含来源类型、job信息等上下文
    """
    find_cron_session_list = await oc_list_exec_session_ids_from_sessions_json()

    # 统一的结果列表，每个session都是一条独立记录
    result = []

    # ========== 处理 cron 类型 ==========
    if 'cron' in find_cron_session_list:
        for cron_id, session_ids in find_cron_session_list['cron'].items():
            for idx, session_id in enumerate(session_ids):
                try:
                    messages = await oc_session_id_to_openai_messages(
                        oc_agent_name="main",
                        session_id=session_id
                    )

                    # 尝试从第一条消息中提取任务摘要
                    first_user_msg = ""
                    first_assistant_msg = ""
                    for msg in messages:
                        if msg['role'] == 'user' and not first_user_msg:
                            first_user_msg = msg['content'][:200]  # 截取前200字符
                        if msg['role'] == 'assistant' and msg['content'] and not first_assistant_msg:
                            first_assistant_msg = msg['content'][:200]
                        if first_user_msg and first_assistant_msg:
                            break

                    record = {
                        "source_type": "cron",  # 来源类型: cron / heartbeat
                        "cron_id": cron_id,  # 所属的 cron job ID
                        "session_id": session_id,  # 会话 ID
                        "execution_index": idx,  # 第几次执行（0开始）
                        "total_executions": len(session_ids),  # 该job总共执行了几次
                        "message_count": len(messages),  # 消息条数
                        "messages": messages,  # 完整消息列表
                        "first_user_message": first_user_msg,  # 第一条用户消息（快速预览）
                        "first_assistant_message": first_assistant_msg,  # 第一条助手回复（快速预览）
                        "status": "success"
                    }

                    result.append(record)
                    print(
                        f"✅ [cron] job={cron_id[:8]}... 第{idx + 1}/{len(session_ids)}次执行, session={session_id[:8]}..., {len(messages)}条消息")

                except Exception as e:
                    result.append({
                        "source_type": "cron",
                        "cron_id": cron_id,
                        "session_id": session_id,
                        "execution_index": idx,
                        "total_executions": len(session_ids),
                        "message_count": 0,
                        "messages": [],
                        "first_user_message": "",
                        "first_assistant_message": "",
                        "status": "error",
                        "error": str(e)
                    })
                    print(f"❌ [cron] job={cron_id[:8]}... session={session_id[:8]}... 失败: {e}")

    # ========== 处理 heartbeat 类型 ==========
    if 'heartbeat' in find_cron_session_list:
        heartbeat_sessions = find_cron_session_list['heartbeat']
        for idx, session_id in enumerate(heartbeat_sessions):
            try:
                messages = await oc_session_id_to_openai_messages(
                    oc_agent_name="main",
                    session_id=session_id
                )

                first_user_msg = ""
                first_assistant_msg = ""
                for msg in messages:
                    if msg['role'] == 'user' and not first_user_msg:
                        first_user_msg = msg['content'][:200]
                    if msg['role'] == 'assistant' and msg['content'] and not first_assistant_msg:
                        first_assistant_msg = msg['content'][:200]
                    if first_user_msg and first_assistant_msg:
                        break

                record = {
                    "source_type": "heartbeat",  # 来源类型
                    "cron_id": None,  # heartbeat没有cron_id
                    "session_id": session_id,
                    "execution_index": idx,
                    "total_executions": len(heartbeat_sessions),
                    "message_count": len(messages),
                    "messages": messages,
                    "first_user_message": first_user_msg,
                    "first_assistant_message": first_assistant_msg,
                    "status": "success"
                }

                result.append(record)
                print(
                    f"✅ [heartbeat] 第{idx + 1}/{len(heartbeat_sessions)}次, session={session_id[:8]}..., {len(messages)}条消息")

            except Exception as e:
                result.append({
                    "source_type": "heartbeat",
                    "cron_id": None,
                    "session_id": session_id,
                    "execution_index": idx,
                    "total_executions": len(heartbeat_sessions),
                    "message_count": 0,
                    "messages": [],
                    "first_user_message": "",
                    "first_assistant_message": "",
                    "status": "error",
                    "error": str(e)
                })
                print(f"❌ [heartbeat] session={session_id[:8]}... 失败: {e}")

    return ok(result)


@router.get("/cron/get_runs")
async def get_cron_runs(
    session_id: str = Query(description="对话id"),
    job_session_agent_repo: JobSessionAgentRepository = Depends(get_job_session_agent_repo),
    job_sync_log_repo: JobSyncLogRepository = Depends(get_job_sync_log_repo),
):

    cron_job_list = await run_in_threadpool(
        lambda: job_session_agent_repo.list_by_session_alias(session_alias=session_id)
    )

    result = []
    for cron_job in cron_job_list:
        job_run_history = await read_jsonl_as_list(Path(f"/home/user/.openclaw/cron/runs/{cron_job.job_id}.jsonl"))
        job_push_history = await run_in_threadpool(
            lambda: job_sync_log_repo.list_ts_by_job_id(job_id=cron_job.job_id)
        )

        job_push_ts_set = {int(x) for x in job_push_history if x is not None}
        new_run_logs = [
            row
            for row in job_run_history
            if isinstance(row, dict)
            and isinstance(row.get("ts"), int)
            and row["ts"] not in job_push_ts_set
        ]

        result.append({
            "jobId": cron_job.job_id,
            "runs": new_run_logs,
        })

    return ok(result)


@router.post("/cron/push_runs")
async def push_cron_runs(
    payload: PushCronRunsPayload,
    job_sync_log_repo: JobSyncLogRepository = Depends(get_job_sync_log_repo),
):
    inserted = 0
    skipped = 0

    for item in payload.items:
        ok_inserted = await run_in_threadpool(
            lambda: job_sync_log_repo.insert(job_id=item.job_id, ts=item.ts)
        )
        if ok_inserted:
            inserted += 1
        else:
            skipped += 1

    return ok({"inserted": inserted, "skipped": skipped, "total": len(payload.items)})
