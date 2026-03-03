import datetime
from peewee import AutoField, CharField, TextField, DateTimeField

from app.models.base import BaseModel


class Session(BaseModel):
    id = AutoField()

    session_id = CharField(max_length=36, null=True, unique=True, index=True)  # CC的session_id UUID 格式，可为空
    session_alias = CharField(max_length=255, null=True, unique=True, index=True)  # 会话别名，可为空但唯一

    oc_session_id = CharField(max_length=64, null=True, index=True) # cli命令使用
    oc_session_key = CharField(max_length=128, null=True, index=True) # chat/completions接口使用
    oc_agent_id = CharField(max_length=64, null=True, index=True) # 记录OC的agent， 通过agent + /new生成新的oc session

    note = TextField(null=True)  # 备注信息

    workspace_path = TextField(null=True)  # 对应的工作区路径

    deploy_id = CharField(max_length=64, null=True, index=True)  # 部署ID（初始可为空）

    last_used_at = DateTimeField(null=True, index=True)  # 最后使用时间
    created_at = DateTimeField(default=datetime.datetime.utcnow)
    updated_at = DateTimeField(default=datetime.datetime.utcnow)

    class Meta:
        table_name = "sessions"

    def save(self, *args, **kwargs):
        self.updated_at = datetime.datetime.utcnow()
        return super().save(*args, **kwargs)
