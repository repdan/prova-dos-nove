"""
Escolher o melhor filtro POR ATIVO funciona fora do periodo em que foi escolhido?

    .venv/Scripts/python.exe -m analises.ichimoku_filtro_por_ativo

1) A hipotese do autor, fixada agora: ouro com F2 (tenkan x kijun), USDJPY sem
   filtro. Testada em 2025-2026, periodo que nenhum filtro do ouro viu.
2) O mesmo procedimento ("escolher o melhor filtro de cada ativo no passado")
   aplicado a seis ativos: escolhe na 1a metade, mede na 2a. Se o procedimento
   funcionasse, o filtro escolhido deveria vencer o "sem filtro" na maioria.
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from analises.ichimoku_filtros import FILTROS, resumo, rodar   # noqa: E402

# (ativo, periodo de escolha, periodo de teste)
PERIODOS = {"ouro": ((2022, 2024), (2025, 2026)), "USDJPY": ((2022, 2024), (2025, 2026)),
            "GBPUSD": ((2022, 2024), (2025, 2026)), "AUDUSD": ((2022, 2024), (2025, 2026)),
            "USDCAD": ((2022, 2024), (2025, 2026)), "EURUSD": ((2024, 2024), (2025, 2026))}


def main() -> int:
    specs = [(mk, c) for mk in PERIODOS for c in [()] + [(f,) for f in FILTROS]]
    with ProcessPoolExecutor(max_workers=min(4, os.cpu_count())) as ex:
        res = dict(ex.map(rodar, specs, chunksize=1))

    print("\n  1) HIPOTESE: ouro com F2, USDJPY sem filtro - teste em 2025-2026 (com custo)")
    for mk, c in [("ouro", ()), ("ouro", ("F2 tenkan x kijun",)), ("USDJPY", ())]:
        x = resumo(res[(mk, c)], (2025, 2026))
        print(f"    {mk:<8}{' + '.join(c) or 'sem filtro':<22}{x['n']:>6} trades  {x['r']:+.3f} R/trade  {x['ano']:+7.1f} R/ano")

    print("\n  2) PROCEDIMENTO 'melhor filtro por ativo': escolhe no 1o periodo, mede no 2o (com custo, R/ano)")
    print(f"    {'ativo':<8}{'escolhido no passado':<24}{'no passado':>12}{'sem filtro':>12}"
          f"{'| depois:':>10}{' escolhido':>11}{'sem filtro':>12}  venceu?")
    venceu = 0
    for mk, (esc, teste) in PERIODOS.items():
        melhor = max([(f,) for f in FILTROS], key=lambda c: resumo(res[(mk, c)], esc)["ano"])
        a, a0 = resumo(res[(mk, melhor)], esc)["ano"], resumo(res[(mk, ())], esc)["ano"]
        b, b0 = resumo(res[(mk, melhor)], teste)["ano"], resumo(res[(mk, ())], teste)["ano"]
        # Se nada bate o "sem filtro" no passado, o procedimento escolhe nao filtrar.
        if a <= a0:
            melhor, a, b = ("(nenhum)",), a0, b0
        venceu += b > b0
        print(f"    {mk:<8}{melhor[0]:<24}{a:>+12.1f}{a0:>+12.1f}{'':>10}{b:>+11.1f}{b0:>+12.1f}  "
              f"{'sim' if b > b0 else ('igual' if b == b0 else 'nao')}")
    print(f"\n    O filtro escolhido no passado venceu o 'sem filtro' depois em {venceu} de {len(PERIODOS)} ativos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
