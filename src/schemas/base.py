from pydantic import BaseModel, ConfigDict


class StrictRequestModel(BaseModel):

    model_config = ConfigDict(
        extra="forbid",  # reject unknown fields → 422
        str_strip_whitespace=True,  # auto-strip strings
        validate_assignment=True,  # validate on attribute set
    )
