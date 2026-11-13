from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, field_validator, EmailStr, model_validator


class Credentials(BaseModel):
    name: str = Field(min_length=2, max_length=60, pattern=r"^[\w\-\u4e00-\u9fff]+$")
    password: str = Field(min_length=10, max_length=100)
    email: EmailStr | None = None


class CityStay(BaseModel):
    city: str = Field(min_length=1, max_length=40)
    days: int = Field(ge=1, le=14)


class Requirements(BaseModel):
    city_stays: list[CityStay] = Field(default_factory=list, max_length=4)
    city: str = Field(default="北京", min_length=1, max_length=40)
    origin: str = Field(default="", max_length=100)
    start_date: date | None = None
    days: int = Field(default=3, ge=1, le=14)
    people: int = Field(default=1, ge=1, le=12)
    budget: int | None = Field(default=None, ge=1, le=1000000)
    transport: Literal["public_transit", "walk", "drive"] = "public_transit"
    style: Literal["city", "outdoor"] = "city"
    max_walk_meters: int = Field(default=8000, ge=500, le=30000)
    interests: str = Field(default="历史文化、公园与街区", max_length=500)
    locked_ids: list[str] = Field(default_factory=list, max_length=15)
    excluded_ids: list[str] = Field(default_factory=list, max_length=30)
    indoor_only: bool = False
    needs_accommodation: bool | None = None

    @model_validator(mode="after")
    def consistent_cities(self):
        if self.city_stays:
            total = sum(s.days for s in self.city_stays)
            if total > 14:
                raise ValueError("多城市总行程最长 14 天")
            if "days" in self.model_fields_set and self.days != total:
                raise ValueError("各城市天数之和必须等于总天数")
            if "city" in self.model_fields_set and self.city != self.city_stays[0].city:
                raise ValueError("主城市必须是第一站")
            self.days = total
            self.city = self.city_stays[0].city
        return self


def day_cities(req):
    return (
        [stay.city for stay in req.city_stays for _ in range(stay.days)]
        if req.city_stays
        else [req.city] * req.days
    )


class RunRequest(BaseModel):
    trip_id: str | None = None
    base_version: int = Field(default=0, ge=0)
    request_key: str = Field(min_length=8, max_length=100)
    message: str = Field(min_length=1, max_length=4000)
    requirements: Requirements = Field(default_factory=Requirements)
    strategy: Literal["multi", "single", "pure"] = "multi"
    fixture: bool = False
    fixture_model: bool = False
    conversation_id: str | None = None
    allow_undated_draft: bool = False
    compare: bool = False
    regenerate: bool = False


class ResumeRequest(BaseModel):
    requirements: Requirements


class PlanSelection(BaseModel):
    days: list[list[str]] = Field(description="每日候选地点 ID，不能新增 ID")
    rationale: str = Field(max_length=2000, description="安排理由、取舍与尚未确认的条件")


class DelegateSelection(BaseModel):
    domains: list[Literal["destination", "transport", "lodging", "knowledge"]]
    reasoning: str = Field(max_length=1000)


class TripPatch(BaseModel):
    version: int = Field(ge=1)
    locked_ids: list[str] = Field(max_length=15)

    @field_validator("locked_ids")
    @classmethod
    def unique(cls, value):
        return list(dict.fromkeys(value))
