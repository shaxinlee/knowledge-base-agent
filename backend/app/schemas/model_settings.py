from pydantic import BaseModel


class ModelEndpointSettings(BaseModel):
    base_url: str = ""
    api_key: str = ""
    model: str = ""


class ModelSettingsResponse(BaseModel):
    mineru: ModelEndpointSettings
    llm: ModelEndpointSettings
    document_summary: ModelEndpointSettings
    text_embedding: ModelEndpointSettings
    reranker: ModelEndpointSettings
    intent_recognition: ModelEndpointSettings
    knowledge_search_classifier: ModelEndpointSettings
    image_description: ModelEndpointSettings
    multimodal_embedding: ModelEndpointSettings


class ModelSettingsUpdateRequest(ModelSettingsResponse):
    pass
