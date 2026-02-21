from .BaseDataModel import BaseDataModel
from .DB_schemas.usage_log import UsageLog
from pymongo import IndexModel


class UsageLogModel(BaseDataModel):
    collection_setting_key: str = "USAGE_LOGS_COLLECTION"

    def __init__(self, db_client: object):
        super().__init__(db_client=db_client)

    @classmethod
    async def create_instance(cls, db_client: object):
        instance = cls(db_client=db_client)
        await instance.init_collection()
        return instance

    async def init_collection(self):
        indexes = UsageLog.get_indexes()
        models = []
        for index in indexes:
             keys = index['fields']
             models.append(IndexModel(
                keys,
                name=index['name'],
                unique=index.get('unique', False)
             ))
        
        if models:
            try:
                await self.collection.create_indexes(models)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to create indexes for UsageLogModel collection: {e}")

    async def log_usage(self, usage_data: UsageLog):
        data = usage_data.model_dump(by_alias=True, exclude_none=True)
        result = await self.collection.insert_one(data)
        return result.inserted_id

    async def get_project_summary(self, project_id: str) -> dict:
        """Full project summary with breakdowns by action and model."""
        # Overall totals
        totals_pipeline = [
            {"$match": {"project_id": project_id}},
            {"$group": {
                "_id": None,
                "total_input_tokens": {"$sum": "$prompt_tokens"},
                "total_output_tokens": {"$sum": "$completion_tokens"},
                "total_tokens": {"$sum": "$total_tokens"},
                "average_latency_ms": {"$avg": "$latency_ms"},
                "total_requests": {"$sum": 1}
            }}
        ]
        cursor = await self.collection.aggregate(totals_pipeline)
        totals = await cursor.to_list(length=1)

        summary = {
            "project_id": project_id,
            "total_requests": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "average_latency_ms": 0,
            "by_action": {},
            "by_model": {}
        }

        if totals:
            t = totals[0]
            summary.update({
                "total_requests": t["total_requests"],
                "total_input_tokens": t["total_input_tokens"],
                "total_output_tokens": t["total_output_tokens"],
                "total_tokens": t["total_tokens"],
                "average_latency_ms": round(t["average_latency_ms"] or 0),
            })

        # Breakdown by action type
        action_pipeline = [
            {"$match": {"project_id": project_id}},
            {"$group": {
                "_id": "$action_type",
                "count": {"$sum": 1},
                "input_tokens": {"$sum": "$prompt_tokens"},
                "output_tokens": {"$sum": "$completion_tokens"},
                "total_tokens": {"$sum": "$total_tokens"},
                "avg_latency_ms": {"$avg": "$latency_ms"}
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
                "avg_latency_ms": round(a["avg_latency_ms"] or 0)
            }

        # Breakdown by model
        model_pipeline = [
            {"$match": {"project_id": project_id}},
            {"$group": {
                "_id": "$model_id",
                "count": {"$sum": 1},
                "input_tokens": {"$sum": "$prompt_tokens"},
                "output_tokens": {"$sum": "$completion_tokens"},
                "total_tokens": {"$sum": "$total_tokens"},
                "avg_latency_ms": {"$avg": "$latency_ms"}
            }}
        ]
        cursor = await self.collection.aggregate(model_pipeline)
        models = await cursor.to_list(length=100)
        for m in models:
            summary["by_model"][m["_id"]] = {
                "count": m["count"],
                "input_tokens": m["input_tokens"],
                "output_tokens": m["output_tokens"],
                "total_tokens": m["total_tokens"],
                "avg_latency_ms": round(m["avg_latency_ms"] or 0)
            }

        return summary

    async def get_usage_by_file(self, project_id: str) -> list[dict]:
        """Per-file usage breakdown."""
        pipeline = [
            {"$match": {"project_id": project_id, "file_id": {"$ne": None}}},
            {"$group": {
                "_id": "$file_id",
                "total_input_tokens": {"$sum": "$prompt_tokens"},
                "total_output_tokens": {"$sum": "$completion_tokens"},
                "total_tokens": {"$sum": "$total_tokens"},
                "average_latency_ms": {"$avg": "$latency_ms"},
                "request_count": {"$sum": 1},
                "actions": {"$addToSet": "$action_type"},
                "models": {"$addToSet": "$model_id"}
            }},
            {"$sort": {"total_tokens": -1}}
        ]
        cursor = await self.collection.aggregate(pipeline)
        results = await cursor.to_list(length=1000)

        return [
            {
                "file_id": r["_id"],
                "total_input_tokens": r["total_input_tokens"],
                "total_output_tokens": r["total_output_tokens"],
                "total_tokens": r["total_tokens"],
                "average_latency_ms": round(r["average_latency_ms"] or 0),
                "request_count": r["request_count"],
                "actions": r["actions"],
                "models": r["models"]
            }
            for r in results
        ]

    async def delete_by_project_id(self, project_id: str):
        result = await self.collection.delete_many({"project_id": project_id})
        return result.deleted_count

    async def get_usage_logs(self, project_id: str, page: int = 1, page_size: int = 50) -> dict:
        """Raw log listing with pagination."""
        skip = (page - 1) * page_size

        total = await self.collection.count_documents({"project_id": project_id})

        cursor = self.collection.find(
            {"project_id": project_id}
        ).sort("timestamp", -1).skip(skip).limit(page_size)

        records = await cursor.to_list(length=page_size)

        logs = []
        for r in records:
            logs.append({
                "id": str(r.get("_id", "")),
                "file_id": r.get("file_id"),
                "timestamp": r.get("timestamp").isoformat() if r.get("timestamp") else None,
                "model": r.get("model_id"),
                "action": r.get("action_type"),
                "input_tokens": r.get("prompt_tokens", 0),
                "output_tokens": r.get("completion_tokens", 0),
                "total_tokens": r.get("total_tokens", 0),
                "latency_ms": r.get("latency_ms", 0)
            })

        return {
            "project_id": project_id,
            "page": page,
            "page_size": page_size,
            "total_logs": total,
            "total_pages": (total + page_size - 1) // page_size,
            "logs": logs
        }
