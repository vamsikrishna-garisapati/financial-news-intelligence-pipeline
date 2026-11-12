"""Company persistence helpers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Company
from app.services.processing import CompanyRef


class CompanyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_ticker(self, ticker: str) -> Company | None:
        stmt = select(Company).where(Company.ticker == ticker.upper())
        return self.db.scalar(stmt)

    def upsert_many(self, refs: list[CompanyRef]) -> list[Company]:
        companies: list[Company] = []
        for ref in refs:
            ticker = ref.ticker.upper()
            company = self.get_by_ticker(ticker)
            if company is None:
                company = Company(
                    ticker=ticker,
                    name=ref.name,
                    exchange=ref.exchange,
                    sector=ref.sector,
                )
                self.db.add(company)
                self.db.flush()
            else:
                if ref.name and not company.name:
                    company.name = ref.name
                if ref.exchange and not company.exchange:
                    company.exchange = ref.exchange
                if ref.sector and not company.sector:
                    company.sector = ref.sector
            companies.append(company)
        return companies
