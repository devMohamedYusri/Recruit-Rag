from .BaseDataModel import BaseDataModel
from .DB_schemas.usage_log import UsageLog
from pymongo import IndexModel
import logging

logger = logging.getLogger(__name__)


class UsageLogModel(BaseDataModel):
    """Model for managing usage logs and token tracking in MongoDB."""
    collection_setting_key: str = "USAGE_LOGS_COLLECTION"

    def __init__(self, db_client: object):
        super().__init__(db_client=db_client)

    @classmethod
    async def create_instance(cls, db_client: object):
        """Creates an instance and initializes the collection indexes."""
        instance = cls(db_client=db_client)
        await instance.init_collection()
        return instance


    async def init_collection(self):
        indexes = UsageLog.get_indexes()
        models = [
            IndexModel(
                index['fields'],
                name=index['name'],
                unique=index.get('unique', False)
            ) for index in indexes
        ]
        if models:
            try:
                await self.collection.create_indexes(models)
            except Exception as e:
                logger.warning(f"Failed to create indexes for UsageLogModel: {e}")

    @property
    def _write_sem(self):
        if not hasattr(self, "__write_sem"):
            import asyncio
            self.__write_sem = asyncio.Semaphore(20)
        return self.__write_sem

    async def log_usage(self, log_data: UsageLog):
        data = log_data.model_dump(by_alias=True)
        # remove None _id to rely on mongo auto-gen if needed
        if data.get("_id") is None:
            del data["_id"]
        
        async with self._write_sem:
            result = await self.collection.insert_one(data)
            return result.inserted_id

    async def get_project_summary(self, project_id: str, user_id: object) -> dict:
        """Full project summary with breakdowns by action_type."""
        totals_pipeline = [
            {"$match": {"project_id": project_id, "user_id": user_id}},
            {"$group": {
                "_id": None,
                "total_tokens": {"$sum": "$total_tokens"},
                "total_input_tokens": {"$sum": "$prompt_tokens"},
                "total_output_tokens": {"$sum": "$completion_tokens"},
                "total_requests": {"$sum": 1},
                "avg_latency_ms": {"$avg": "$latency_ms"},
            }}
        ]
        cursor = await self.collection.aggregate(totals_pipeline)
        totals = await cursor.to_list(length=1)

        summary = {
            "project_id": project_id,
            "total_requests": 0,
            "total_tokens": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "average_latency_ms": 0,
            "by_action": {}
        }

        if totals:
            t = totals[0]
            summary.update({
                "total_requests": t["total_requests"],
                "total_tokens": t["total_tokens"],
                "total_input_tokens": t["total_input_tokens"],
                "total_output_tokens": t["total_output_tokens"],
                "average_latency_ms": round(t.get("avg_latency_ms") or 0),
            })

        action_pipeline = [
            {"$match": {"project_id": project_id, "user_id": user_id}},
            {"$group": {
                "_id": "$action_type",
                "count": {"$sum": 1},
                "input_tokens": {"$sum": "$prompt_tokens"},
                "output_tokens": {"$sum": "$completion_tokens"},
                "total_tokens": {"$sum": "$total_tokens"},
                "avg_latency_ms": {"$avg": "$latency_ms"},
            }}
        ]
        cursor = await self.collection.aggregate(action_pipeline)
        actions = await cursor.to_list(length=100)
        for a in actions:
            summary["by_action"][a["_id"]] = {
                "count": a["count"],
                "input_tokens": a["input_tokens"],
                "output_tokens": a["output_tokens"],
                "total_tokens": a["total_tokens"],
                "avg_latency_ms": round(a.get("avg_latency_ms") or 0),
            }

        return summary

    async def delete_by_project_id(self, project_id: str, user_id: object):
        result = await self.collection.delete_many({"project_id": project_id, "user_id": user_id})
        return result.deleted_count

    async def get_usage_logs(self, user_id: object, project_id: str = None, page: int = 1, page_size: int = 50) -> dict:
        """Raw log listing with pagination."""
        skip = (page - 1) * page_size
        query = {"user_id": user_id}
        if project_id:
            query["project_id"] = project_id

        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(page_size)
        records = await cursor.to_list(length=page_size)

        logs = []
        for r in records:
            logs.append({
                "id": str(r.get("_id", "")),
                "project_id": r.get("project_id"),
                "file_id": r.get("file_id"),
                "model": r.get("model_id"),
                "action": r.get("action_type"),
                "input_tokens": r.get("prompt_tokens", 0),
                "output_tokens": r.get("completion_tokens", 0),
                "total_tokens": r.get("total_tokens", 0),
                "latency_ms": r.get("latency_ms", 0),
                "timestamp": r.get("created_at").isoformat() if r.get("created_at") else None,
            })

        return {
            "user_id": str(user_id),
            "project_id": project_id,
            "page": page,
            "page_size": page_size,
            "total_logs": total,
            "total_pages": (total + page_size - 1) // page_size,
            "logs": logs
        }

    async def get_files_breakdown(self, project_id: str, user_id: object) -> dict:
        """Per-file token and request breakdown for a project."""
        pipeline = [
            {"$match": {"project_id": project_id, "user_id": user_id, "file_id": {"$ne": None}}},
            {"$group": {
                "_id": "$file_id",
                "total_tokens": {"$sum": "$total_tokens"},
                "request_count": {"$sum": 1},
                "actions": {"$addToSet": "$action_type"},
                "models": {"$addToSet": "$model_id"},
            }},
            {"$sort": {"total_tokens": -1}}
        ]
        cursor = await self.collection.aggregate(pipeline)
        records = await cursor.to_list(length=None)

        files = [
            {
                "file_id": r["_id"],
                "total_tokens": r["total_tokens"],
                "request_count": r["request_count"],
                "actions": r["actions"],
                "models": r["models"],
            }
            for r in records
        ]
        return {"project_id": project_id, "files": files}
