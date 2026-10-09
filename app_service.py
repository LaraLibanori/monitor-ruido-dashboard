# =============================================
# app_service.py - Regras de apresentação do app
# =============================================
# Junta dados do banco (database.py) com a regra do
# silêncio (silence_policy.py) e devolve respostas
# prontas para o aplicativo Android.
# Não tem SQL aqui e não tem HTTP aqui.
# =============================================

from datetime import date, datetime, time
import os

from database import Database
from silence_policy import policy

# Sem leitura há mais que isso = sensor "sem sinal" (o ESP32 envia a cada ~5 s)
OFFLINE_AFTER_SECONDS = int(os.getenv("OFFLINE_AFTER_SECONDS", 60))

_LEVELS = ["baixo", "medio", "alto", "muito_alto"]


class HouseNotFound(Exception):
    pass


class AppService:
    def __init__(self, db: Database):
        self.db = db

    def overview(self) -> dict:
        """Tela inicial: status do silêncio + uma entrada por casa."""
        day_start_utc, _ = policy.day_bounds_utc(policy.today())
        houses = []
        for row in self.db.get_houses_overview(day_start_utc):
            seconds = row["seconds_since_last"]
            has_reading = seconds is not None
            houses.append({
                "sensor_id": row["sensor_id"],
                "name": row["display_name"],
                "location": row["location"],
                "online": has_reading and seconds <= OFFLINE_AFTER_SECONDS,
                "seconds_since_last": seconds,
                "last_reading": {
                    "rms": row["rms"],
                    "noise_level": row["noise_level"],
                    "is_silence_period": row["is_silence_period"],
                } if has_reading else None,
                "today": {
                    "readings": row["today_readings"],
                    "loud_in_silence": row["today_loud_in_silence"],
                },
            })
        return {"silence": policy.status(), "houses": houses}

    def history(self, sensor_id: str, day: date | None = None) -> dict:
        """Tela da casa: 24 barras (uma por hora) do dia escolhido."""
        house = self.db.get_house(sensor_id)
        if house is None:
            raise HouseNotFound(sensor_id)

        day = day or policy.today()
        start_utc, end_utc = policy.day_bounds_utc(day)
        rows = {
            r["hour"]: r
            for r in self.db.get_hourly_history(sensor_id, start_utc, end_utc, policy.tz_name)
        }

        buckets = []
        for hour in range(24):
            r = rows.get(hour)
            hour_start = datetime.combine(day, time(hour, 0), tzinfo=policy.tz)
            buckets.append({
                "hour": hour,
                "is_silence": policy.is_silence(hour_start),
                "readings": r["readings"] if r else 0,
                "avg_rms": round(r["avg_rms"], 1) if r else None,
                "max_rms": round(r["max_rms"], 1) if r else None,
                "worst_level": _LEVELS[r["worst_level_order"]] if r else None,
                "loud": r["loud"] if r else 0,
                "loud_in_silence": r["loud_in_silence"] if r else 0,
            })

        with_data = [b for b in buckets if b["readings"]]
        loudest = max(with_data, key=lambda b: b["avg_rms"], default=None)
        return {
            "sensor_id": house["sensor_id"],
            "name": house["display_name"],
            "location": house["location"],
            "date": day.isoformat(),
            "buckets": buckets,
            "summary": {
                "readings": sum(b["readings"] for b in buckets),
                "loud": sum(b["loud"] for b in buckets),
                "loud_in_silence": sum(b["loud_in_silence"] for b in buckets),
                "loudest_hour": loudest["hour"] if loudest else None,
            },
        }
