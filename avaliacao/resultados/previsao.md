# Resultados — previsão D+1 de corte ENE no Nordeste

Gerado por `avaliacao/avaliar_previsao.py`. Período: 2026-01-01 a 2026-09-06 (11.952 patamares de 30 min; 11.616 avaliados, excluída a 1ª semana para todos os métodos terem comparação).

## Regressão (MWmed por patamar)

| método | MAE | RMSE | viés | WAPE % | R² | correlação | MAE quando há corte |
|---|---:|---:|---:|---:|---:|---:|---:|
| **modelo** | 1.309,6 | 2.813,2 | -578,5 | 58,2 | 0,646 | 0,814 | 3.892,3 |
| climatologia | 1.572 | 3.154,5 | -88,3 | 69,8 | 0,555 | 0,748 | 3.876,7 |
| persistência D-1 (otimista) | 1.527,2 | 3.377,3 | -8,5 | 67,8 | 0,490 | 0,745 | 4.213,8 |
| persistência realista (emitida às 12h de D) | 1.728,5 | 3.799,2 | -11,8 | 76,8 | 0,354 | 0,677 | 4.677,8 |
| semanal D-7 | 1.928,8 | 4.109 | -28,5 | 85,7 | 0,245 | 0,620 | 5.077 |

Redução de MAE do modelo: 16,7 % vs climatologia, 14,2 % vs persistência D-1 (otimista), 24,2 % vs persistência realista, 32,1 % vs semanal D-7.

## Classificação binária: "haverá corte ≥ limiar neste patamar?"

### Limiar 200 MWmed (prevalência real: 29,2 % dos patamares)

| método | VP | FP | FN | VN | acurácia % | precisão % | revocação % | especificidade % | F1 % | acurácia balanceada % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **modelo** | 2.793 | 947 | 604 | 7.272 | 86,6 | 74,7 | 82,2 | 88,5 | 78,3 | 85,3 |
| climatologia | 3.182 | 1.904 | 215 | 6.315 | 81,8 | 62,6 | 93,7 | 76,8 | 75,0 | 85,3 |
| persistência D-1 (otimista) | 2.642 | 736 | 755 | 7.483 | 87,2 | 78,2 | 77,8 | 91,0 | 78,0 | 84,4 |
| persistência realista (emitida às 12h de D) | 2.522 | 853 | 875 | 7.366 | 85,1 | 74,7 | 74,2 | 89,6 | 74,5 | 81,9 |
| semanal D-7 | 2.435 | 952 | 962 | 7.267 | 83,5 | 71,9 | 71,7 | 88,4 | 71,8 | 80,0 |

### Limiar 500 MWmed (prevalência real: 28,9 % dos patamares)

| método | VP | FP | FN | VN | acurácia % | precisão % | revocação % | especificidade % | F1 % | acurácia balanceada % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **modelo** | 2.559 | 744 | 793 | 7.520 | 86,8 | 77,5 | 76,3 | 91,0 | 76,9 | 83,7 |
| climatologia | 3.058 | 1.575 | 294 | 6.689 | 83,9 | 66,0 | 91,2 | 80,9 | 76,6 | 86,1 |
| persistência D-1 (otimista) | 2.602 | 731 | 750 | 7.533 | 87,3 | 78,1 | 77,6 | 91,2 | 77,8 | 84,4 |
| persistência realista (emitida às 12h de D) | 2.482 | 848 | 870 | 7.416 | 85,2 | 74,5 | 74,0 | 89,7 | 74,3 | 81,9 |
| semanal D-7 | 2.400 | 942 | 952 | 7.322 | 83,7 | 71,8 | 71,6 | 88,6 | 71,7 | 80,1 |

### Limiar 1.000 MWmed (prevalência real: 27,9 % dos patamares)

| método | VP | FP | FN | VN | acurácia % | precisão % | revocação % | especificidade % | F1 % | acurácia balanceada % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **modelo** | 2.269 | 580 | 975 | 7.792 | 86,6 | 79,6 | 69,9 | 93,1 | 74,5 | 81,5 |
| climatologia | 2.831 | 1.317 | 413 | 7.055 | 85,1 | 68,2 | 87,3 | 84,3 | 76,6 | 85,8 |
| persistência D-1 (otimista) | 2.504 | 722 | 740 | 7.650 | 87,4 | 77,6 | 77,2 | 91,4 | 77,4 | 84,3 |
| persistência realista (emitida às 12h de D) | 2.387 | 837 | 857 | 7.535 | 85,4 | 74,0 | 73,6 | 90,0 | 73,8 | 81,8 |
| semanal D-7 | 2.309 | 929 | 935 | 7.443 | 84,0 | 71,3 | 71,2 | 88,9 | 71,2 | 80,0 |

### Limiar 2.000 MWmed (prevalência real: 24,8 % dos patamares)

| método | VP | FP | FN | VN | acurácia % | precisão % | revocação % | especificidade % | F1 % | acurácia balanceada % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **modelo** | 1.858 | 415 | 1.020 | 8.323 | 87,6 | 81,7 | 64,6 | 95,3 | 72,1 | 79,9 |
| climatologia | 2.369 | 1.097 | 509 | 7.641 | 86,2 | 68,3 | 82,3 | 87,4 | 74,7 | 84,9 |
| persistência D-1 (otimista) | 2.185 | 677 | 693 | 8.061 | 88,2 | 76,3 | 75,9 | 92,3 | 76,1 | 84,1 |
| persistência realista (emitida às 12h de D) | 2.090 | 769 | 788 | 7.969 | 86,6 | 73,1 | 72,6 | 91,2 | 72,9 | 81,9 |
| semanal D-7 | 2.006 | 861 | 872 | 7.877 | 85,1 | 70,0 | 69,7 | 90,1 | 69,8 | 79,9 |

## Sinal de três níveis (VERMELHO < 200 ≤ AMARELO < 1.000 ≤ VERDE, limiares da equipe)

| método | acurácia % | F1 macro % | kappa | F1 VERMELHO % | F1 AMARELO % | F1 VERDE % |
|---|---:|---:|---:|---:|---:|---:|
| **modelo** | 82,4 | 56,8 | 0,609 | 90,4 | 5,6 | 74,5 |
| climatologia | 79,0 | 56,0 | 0,581 | 85,6 | 5,9 | 76,6 |
| persistência D-1 (otimista) | 86,0 | 57,4 | 0,668 | 90,9 | 3,9 | 77,4 |
| persistência realista (emitida às 12h de D) | 84,1 | 56,8 | 0,621 | 89,5 | 7,2 | 73,8 |
| semanal D-7 | 82,5 | 55,0 | 0,584 | 88,4 | 5,3 | 71,2 |

Matriz de confusão do modelo (linhas = real, colunas = previsto):

| real \ previsto | VERMELHO | AMARELO | VERDE | precisão % | revocação % |
|---|---:|---:|---:|---:|---:|
| VERMELHO | 7.272 | 419 | 528 | 92,3 | 88,5 |
| AMARELO | 72 | 29 | 52 | 3,3 | 19,0 |
| VERDE | 532 | 443 | 2.269 | 79,6 | 69,9 |

## Energia do dia e hora de pico

- Energia diária (249 dias): MAE 27.150 MWh/dia (climatologia 33.103), WAPE 50,9 %, R² 0,491, correlação 0,760; média real 53.389 MWh/dia.
- Hora de maior corte (201 dias com corte): exata em 40,8 %, ±1 h em 69,2 %, ±2 h em 82,1 %.

## Por mês (MAE em MWmed)

| mês | modelo | climatologia | corte real médio |
|---|---:|---:|---:|
| 01/2026 | 1.054 | 1.423 | 1.137 |
| 02/2026 | 523 | 985 | 700 |
| 03/2026 | 1.136 | 1.026 | 1.446 |
| 04/2026 | 1.174 | 1.113 | 2.052 |
| 05/2026 | 1.484 | 1.638 | 2.752 |
| 06/2026 | 1.369 | 2.070 | 1.980 |
| 07/2026 | 1.733 | 2.148 | 3.620 |
| 08/2026 | 1.687 | 1.822 | 3.949 |
| 09/2026 | 2.059 | 2.333 | 2.220 |
