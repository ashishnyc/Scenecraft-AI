# Import all models so SQLAlchemy can resolve relationships between them
from app.models.user import User  # noqa: F401
from app.models.workspace import Workspace  # noqa: F401
from app.models.character import Character, CharacterCasting  # noqa: F401
from app.models.project import Project  # noqa: F401
from app.models.task import Task  # noqa: F401
from app.models.subtask import Subtask  # noqa: F401
from app.models.review_action import ReviewAction  # noqa: F401
from app.models.competitor_video import CompetitorVideo  # noqa: F401
from app.models.trending_topic import TrendingTopic  # noqa: F401
from app.models.pitch import Pitch  # noqa: F401
from app.models.instagram import InstagramPost, InstagramComment  # noqa: F401
from app.models.workspace_ai_config import WorkspaceAIConfig  # noqa: F401
from app.models.workspace_ai_model_config import WorkspaceAIModelConfig  # noqa: F401
