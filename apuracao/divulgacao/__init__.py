"""Divulgação de resultados em tempo real do TSE (resultados.tse.jus.br), eleições 2026.

  cliente  — HTTP com limite de taxa, ETag/304, 404 memorizado, detecção de página HTML
  modelo   — parse puro dos JSON (EA11/EA12/EA14/EA15/EA20) para tabelas Polars
  coletor  — ciclo incremental (só baixa o que mudou) e persistência dos snapshots

Formato observado e regras de coleta: docs/divulgacao_2026_formato_json.md
"""
