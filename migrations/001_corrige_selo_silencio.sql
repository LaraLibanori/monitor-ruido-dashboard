-- =============================================
-- 001_corrige_selo_silencio.sql
-- Recalcula capture_hour e is_silence_period das
-- leituras antigas, que foram gravadas com o relógio
-- do container em UTC (3h de diferença).
--
-- Regra = convenção do Ed. Letícia:
--   seg–sex: silêncio 22h–9h | sáb–dom: silêncio 15h–9h
-- Se mudar os horários no .env, ajuste aqui também.
--
-- Aplicada automaticamente (uma única vez) quando a API inicia.
-- Pode rodar de novo sem problema: só recalcula os mesmos valores.
-- =============================================

WITH local AS (
    SELECT id,
           (received_at AT TIME ZONE 'America/Sao_Paulo') AS t
    FROM noise_readings
)
UPDATE noise_readings r
SET capture_hour      = EXTRACT(HOUR FROM l.t)::SMALLINT,
    is_silence_period = (
        l.t::time < TIME '09:00'
        OR (EXTRACT(ISODOW FROM l.t) <= 5 AND l.t::time >= TIME '22:00')
        OR (EXTRACT(ISODOW FROM l.t) >= 6 AND l.t::time >= TIME '15:00')
    )
FROM local l
WHERE r.id = l.id;
