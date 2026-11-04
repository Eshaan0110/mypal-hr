from pydantic import BaseModel


class InfoResponse(BaseModel):
    app: str
    # What the loaded policies are, e.g. "fictional sample policies".
    data_notice: str
