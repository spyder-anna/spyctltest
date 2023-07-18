from typing import List, Union

import spyctl.schemas_v2 as schemas
from fastapi import APIRouter
from pydantic import BaseModel, Field, Json
from typing_extensions import Annotated

import app.commands.diff as cmd_diff

router = APIRouter(prefix="/api/v1")

PrimaryObject = Annotated[
    Union[schemas.GuardianBaselineModel, schemas.GuardianPolicyModel],
    Field(discriminator="kind"),
]

DiffObject = Annotated[
    Union[
        schemas.GuardianBaselineModel,
        schemas.GuardianFingerprintModel,
        schemas.GuardianFingerprintGroupModel,
        schemas.GuardianPolicyModel,
        schemas.UidListModel,
    ],
    Field(discriminator="kind"),
]

# ------------------------------------------------------------------------------
# Diff Object(s) into Object
# ------------------------------------------------------------------------------


class DiffHandlerInput(BaseModel):
    object: Json[PrimaryObject] = Field(title="The primary object of the diff")
    diff_objects: Json[List[DiffObject]] = Field(
        title="The object(s) to diff with the primary object."
    )
    org_uid: str
    api_key: str
    api_url: str


class DiffHandlerOutput(BaseModel):
    diff_data: str


@router.post("/diff")
def diff(
    i: DiffHandlerInput,
) -> DiffHandlerOutput:
    diff_objects = [
        obj.dict(by_alias=True, exclude_unset=True) for obj in i.diff_objects
    ]
    cmd_input = cmd_diff.DiffInput(
        i.object.dict(by_alias=True, exclude_unset=True),
        diff_objects,
        i.org_uid,
        i.api_key,
        i.api_url,
    )
    output = cmd_diff.diff(cmd_input)
    return DiffHandlerOutput(diff_data=output.diff_data)
