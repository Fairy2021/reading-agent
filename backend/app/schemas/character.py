from pydantic import BaseModel


class CharacterCardResponse(BaseModel):
    identity_summary: str = ""
    personality_summary: str = ""
    speaking_style: str = ""
    values_and_taboo: str = ""


class CharacterStateResponse(BaseModel):
    chapter_index: int
    emotional_state: str = ""
    stance: str = ""
    current_goal: str = ""
    relation_snapshot: str = ""


class CharacterEvidenceResponse(BaseModel):
    chapter_index: int
    excerpt: str
    evidence_type: str


class CharacterSummaryResponse(BaseModel):
    id: str
    canonical_name: str
    first_chapter_index: int | None = None
    mention_count: int
    confidence: float
    is_verified: bool = False
    aliases: list[str] = []
    card_preview: str | None = None


class CharacterDetailResponse(BaseModel):
    id: str
    canonical_name: str
    first_chapter_index: int | None = None
    mention_count: int
    confidence: float
    is_verified: bool = False
    aliases: list[str] = []
    card: CharacterCardResponse | None = None
    latest_state: CharacterStateResponse | None = None
    evidences: list[CharacterEvidenceResponse] = []


class RelationshipEdgeResponse(BaseModel):
    id: str
    source_character_id: str
    source_name: str
    target_character_id: str
    target_name: str
    relation_type: str
    strength: float
    first_chapter_index: int | None = None
    last_chapter_index: int | None = None
    evidence_excerpt: str


class RelationshipGraphNodeMetricResponse(BaseModel):
    character_id: str
    canonical_name: str
    degree: int = 0
    in_degree: int = 0
    out_degree: int = 0
    weighted_degree: float = 0.0
    relation_diversity: int = 0
    last_chapter_index: int | None = None


class CharacterPortraitResponse(BaseModel):
    id: str
    character_id: str
    canonical_name: str
    unlocked_chapter_index: int
    status: str
    style_prompt: str = ""
    image_url: str = ""
    generator: str = "pending"


class SkillRunRequest(BaseModel):
    skill_names: list[str] | None = None
    chapter_index: int | None = None
    incremental: bool = True
