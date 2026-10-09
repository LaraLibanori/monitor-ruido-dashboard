# =============================================
# silence_policy.py - Regras do horário de silêncio
# =============================================
# Fonte ÚNICA da verdade sobre "é horário de silêncio?".
# O backend usa para marcar cada leitura e o dashboard
# pergunta para a API (endpoint /api/silence-status).
#
# Padrão = convenção do Condomínio Edifício Letícia:
#   - Segunda a sexta: silêncio das 22h às 9h
#   - Sábado e domingo: barulho só das 9h às 15h
#     (ou seja, silêncio das 15h às 9h)
#
# Tudo é configurável por variável de ambiente, assim
# outro condomínio pode ter outra convenção sem mexer no código.
# =============================================

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import os


def _parse_hhmm(value: str) -> time:
    """Converte '22:00' em datetime.time(22, 0)."""
    hours, minutes = value.strip().split(":")
    return time(int(hours), int(minutes))


@dataclass(frozen=True)
class SilencePolicy:
    tz_name: str
    weekday_start: time   # início do silêncio de segunda a sexta
    weekend_start: time   # início do silêncio no sábado e domingo
    end: time             # fim do silêncio (manhã), todos os dias

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.tz_name)

    @classmethod
    def from_env(cls) -> "SilencePolicy":
        return cls(
            tz_name=os.getenv("APP_TIMEZONE", "America/Sao_Paulo"),
            weekday_start=_parse_hhmm(os.getenv("SILENCE_START_WEEKDAY", "22:00")),
            weekend_start=_parse_hhmm(os.getenv("SILENCE_START_WEEKEND", "15:00")),
            end=_parse_hhmm(os.getenv("SILENCE_END", "09:00")),
        )

    def to_local(self, moment: datetime) -> datetime:
        """Converte qualquer datetime (com fuso) para o horário do condomínio."""
        if moment.tzinfo is None:
            raise ValueError("Use datetimes com fuso (ex.: datetime.now(timezone.utc)).")
        return moment.astimezone(self.tz)

    def is_silence(self, moment: datetime) -> bool:
        """True se o instante cai no horário de silêncio do condomínio."""
        local = self.to_local(moment)
        now_time = local.time()

        # Madrugada/manhã: a noite anterior sempre continua em silêncio até SILENCE_END
        if now_time < self.end:
            return True

        is_weekend = local.weekday() >= 5  # 5 = sábado, 6 = domingo
        start = self.weekend_start if is_weekend else self.weekday_start
        return now_time >= start

    def next_change(self, moment: datetime) -> dict | None:
        """Quando o horário de silêncio começa ou termina a partir de agora."""
        current = self.is_silence(moment)
        today = self.to_local(moment).date()
        probe = moment.replace(second=0, microsecond=0)
        for _ in range(3 * 24 * 60):  # procura minuto a minuto, até 3 dias
            probe += timedelta(minutes=1)
            if self.is_silence(probe) != current:
                local = self.to_local(probe)
                return {
                    "at": local.strftime("%H:%M"),
                    "day_offset": (local.date() - today).days,  # 0 = hoje, 1 = amanhã
                    "silence_starts": not current,
                }
        return None

    def day_bounds_utc(self, day: date) -> tuple[datetime, datetime]:
        """Início e fim (em UTC) de um dia no fuso do condomínio."""
        start_local = datetime.combine(day, time(0, 0), tzinfo=self.tz)
        end_local = datetime.combine(day + timedelta(days=1), time(0, 0), tzinfo=self.tz)
        return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)

    def today(self) -> date:
        return self.to_local(datetime.now(timezone.utc)).date()

    def status(self, moment: datetime | None = None) -> dict:
        """Resumo pronto para a API/dashboard/app."""
        moment = moment or datetime.now(timezone.utc)
        local = self.to_local(moment)
        return {
            "is_silence_period": self.is_silence(moment),
            "next_change": self.next_change(moment),
            "timezone": self.tz_name,
            "local_time": local.strftime("%Y-%m-%d %H:%M:%S"),
            "rules": {
                "weekday": f"{self.weekday_start:%H:%M}–{self.end:%H:%M}",
                "weekend": f"{self.weekend_start:%H:%M}–{self.end:%H:%M}",
            },
        }


# Instância única usada pelo resto do sistema
policy = SilencePolicy.from_env()
