from datetime import datetime, timezone, timedelta, date
from typing import Optional
from sqlalchemy import BigInteger, Boolean, Column, Computed, Date, DateTime, Float, Index, Integer, String, ForeignKey, Text, func
from sqlalchemy.orm import relationship, Mapped, mapped_column

from database.base import Base

# Функция для получения текущего времени в Бишкеке (UTC+6)
def get_kg_time():
    return datetime.now(timezone(timedelta(hours=6)))

class Person(Base):
    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    telegram_id: Mapped[Optional[int]] = mapped_column(
        Integer, unique=True, nullable=True, index=True
    )

    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    full_name: Mapped[Optional[str]] = mapped_column(
        String,
        Computed(
            "TRIM(COALESCE(TRIM(first_name), '') || ' ' || COALESCE(TRIM(last_name), ''))",
            persisted=True
        ),
        nullable=True,
        index=True
    )

    # Теперь nullable=True позволит регистрировать пользователя без телефона
    phone: Mapped[Optional[str]] = mapped_column(
        String, unique=True, nullable=True, index=True
    )

    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False, default="client", index=True)

    # Используем default=get_kg_time для записи времени UTC+6
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=get_kg_time, 
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=get_kg_time,
        onupdate=get_kg_time,
        nullable=False
    )

    last_visit_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    visions: Mapped[list["Vision"]] = relationship(
        "Vision", back_populates="person", cascade="all, delete-orphan"
    )
class Vision(Base):
    __tablename__ = "visions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    visit_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    sph_r: Mapped[float | None] = mapped_column(Float, nullable=True)
    cyl_r: Mapped[float | None] = mapped_column(Float, nullable=True)
    axis_r: Mapped[int | None] = mapped_column(Integer, nullable=True)

    sph_l: Mapped[float | None] = mapped_column(Float, nullable=True)
    cyl_l: Mapped[float | None] = mapped_column(Float, nullable=True)
    axis_l: Mapped[int | None] = mapped_column(Integer, nullable=True)

    pd: Mapped[float | None] = mapped_column(Float, nullable=True)
    lens_type: Mapped[str | None] = mapped_column(String, nullable=True)
    frame_model: Mapped[str | None] = mapped_column(String, nullable=True)
    note: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    person: Mapped["Person"] = relationship(
        "Person",
        back_populates="visions"
    )


class BotContent(Base):
    __tablename__ = "bot_contents"

    key: Mapped[str] = mapped_column(String(30), primary_key=True)  # например: "shop_address", "promotions"
    value: Mapped[str] = mapped_column(Text, nullable=False)



