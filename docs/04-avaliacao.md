# Avaliação — resultados e métricas

Duas avaliações independentes:

1. **Previsão com dados históricos** — o modelo D+1 de corte energético (ENE) do Nordeste, feito
   pela equipe. É a única previsão do projeto; a FlexIA **não faz previsões**, ela consulta dados e
   documentos e explica.
2. **Exatidão da FlexIA** — respostas ponta a ponta com gabarito, e acurácia do roteador NVIDIA.

Resultados completos (todas as tabelas e cada execução):
[avaliacao/resultados/previsao.md](../avaliacao/resultados/previsao.md) ·
[avaliacao/resultados/flexia.md](../avaliacao/resultados/flexia.md) · JSON na mesma pasta.
Para reproduzir: `avaliacao/avaliar_previsao.py` e `avaliacao/avaliar_flexia.py --repeticoes 2`.

---

## 1. Previsão D+1 de corte ENE no Nordeste

### 1.1 Configuração do teste
| item | valor |
|---|---|
| Modelo | `HistGradientBoostingRegressor` (perda absoluta), aprende o resíduo sobre a climatologia |
| Treino | dados até 31/12/2025 |
| Teste (fora da amostra) | 01/01 a 06/09/2026 — 11.952 patamares de 30 min; 11.616 avaliados (1ª semana excluída para todos os comparadores) |
| Alvo | corte ENE do Nordeste por patamar (MWmed); real conferido com o gabarito (diferença máx. 1e-11) |
| Prevalência de corte | 29,2 % dos patamares têm corte ≥ 200 MWmed; 24,8 % ≥ 2.000 MWmed |

Comparadores ("baselines"):

| comparador | definição |
|---|---|
| climatologia | média histórica por mês/semana/patamar (coluna `clima_ne`) |
| persistência D-1 (otimista) | mesmo patamar do dia anterior; na prática indisponível para a tarde de D quando se prevê D+1 |
| **persistência realista** | previsão emitida às 12h de D: manhãs usam D, tardes usam D-1 |
| semanal D-7 | mesmo patamar 7 dias antes |

### 1.2 Métricas de valor (regressão, MWmed por patamar)

| método | MAE | RMSE | viés | WAPE | R² | correlação |
|---|---:|---:|---:|---:|---:|---:|
| **modelo** | **1.309,6** | **2.813,2** | −578,5 | **58,2 %** | **0,646** | **0,814** |
| climatologia | 1.572,0 | 3.154,5 | −88,3 | 69,8 % | 0,555 | 0,748 |
| persistência D-1 (otimista) | 1.527,2 | 3.377,3 | −8,5 | 67,8 % | 0,490 | 0,745 |
| persistência realista | 1.728,5 | 3.799,2 | −11,8 | 76,8 % | 0,354 | 0,677 |
| semanal D-7 | 1.928,8 | 4.109,0 | −28,5 | 85,7 % | 0,245 | 0,620 |

Redução de MAE do modelo: **16,7 %** vs climatologia · **24,2 %** vs persistência realista ·
14,2 % vs persistência otimista · 32,1 % vs semanal.

### 1.3 Métricas de decisão: "haverá corte ≥ 500 MWmed neste patamar?"

| método | VP | FP | FN | VN | acurácia | precisão | revocação | especificidade | F1 | acurácia balanceada |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **modelo** | 2.559 | 744 | 793 | 7.520 | 86,8 % | 77,5 % | 76,3 % | 91,0 % | 76,9 % | 83,7 % |
| climatologia | 3.058 | 1.575 | 294 | 6.689 | 83,9 % | 66,0 % | 91,2 % | 80,9 % | 76,6 % | 86,1 % |
| persistência D-1 (otimista) | 2.602 | 731 | 750 | 7.533 | 87,3 % | 78,1 % | 77,6 % | 91,2 % | 77,8 % | 84,4 % |
| persistência realista | 2.482 | 848 | 870 | 7.416 | 85,2 % | 74,5 % | 74,0 % | 89,7 % | 74,3 % | 81,9 % |
| semanal D-7 | 2.400 | 942 | 952 | 7.322 | 83,7 % | 71,8 % | 71,6 % | 88,6 % | 71,7 % | 80,1 % |

Resumo nos outros limiares (F1 do modelo × persistência realista): 200 MWmed 78,3 % × 74,5 % ·
1.000 MWmed 74,5 % × 73,8 % · 2.000 MWmed 72,1 % × 72,9 %. Com limiares altos o modelo fica mais
preciso (81,7 % a 2.000 MWmed) e perde revocação (64,6 %), consequência do viés para baixo.

### 1.4 Sinal de três níveis (usado pela equipe)
VERMELHO < 200 ≤ AMARELO < 1.000 ≤ VERDE (MWmed previstos), limiares de `ev/sinal.py`.

| método | acurácia | F1 macro | kappa de Cohen | F1 VERMELHO | F1 AMARELO | F1 VERDE |
|---|---:|---:|---:|---:|---:|---:|
| **modelo** | 82,4 % | 56,8 % | 0,609 | 90,4 % | 5,6 % | 74,5 % |
| climatologia | 79,0 % | 56,0 % | 0,581 | 85,6 % | 5,9 % | 76,6 % |
| persistência D-1 (otimista) | 86,0 % | 57,4 % | 0,668 | 90,9 % | 3,9 % | 77,4 % |
| persistência realista | 84,1 % | 56,8 % | 0,621 | 89,5 % | 7,2 % | 73,8 % |
| semanal D-7 | 82,5 % | 55,0 % | 0,584 | 88,4 % | 5,3 % | 71,2 % |

Matriz de confusão do modelo (linhas = real, colunas = previsto):

| real \ previsto | VERMELHO | AMARELO | VERDE | precisão | revocação |
|---|---:|---:|---:|---:|---:|
| VERMELHO | 7.272 | 419 | 528 | 92,3 % | 88,5 % |
| AMARELO | 72 | 29 | 52 | 3,3 % | 19,0 % |
| VERDE | 532 | 443 | 2.269 | 79,6 % | 69,9 % |

### 1.5 Energia do dia e hora de pico
| métrica | modelo |
|---|---|
| Energia diária (249 dias) | MAE 27.150 MWh/dia (climatologia 33.103) sobre média real de 53.389 MWh/dia; WAPE 50,9 %; R² 0,491; correlação 0,760 |
| Hora de maior corte (201 dias com corte) | exata em 40,8 % · ±1 h em 69,2 % · ±2 h em 82,1 % dos dias |

MAE por mês (MWmed): modelo pior que a climatologia em **março** (1.136 × 1.026) e **abril**
(1.174 × 1.113); melhor nos demais meses (maior ganho em junho: 1.369 × 2.070).

### 1.6 Conclusões
1. **Valor em MW:** o modelo é o melhor método em todas as métricas de valor (R² 0,646; MAE 24 %
   menor que a persistência realista), mas o erro ainda é grande em termos absolutos: **WAPE de
   58 %** e **subestimação sistemática de 579 MWmed**.
2. **Decisão "vai ter corte ou não":** acurácia de 86,8 % e F1 de 76,9 % a 500 MWmed — útil, mas
   **praticamente empatado com a persistência realista** (F1 74,3 %) e **abaixo da persistência
   otimista** (77,8 %). O ganho do modelo está no valor, não na decisão binária.
3. **Sinal de três níveis:** acurácia 82,4 % e kappa 0,61 (concordância "substancial"), mas
   **pior que a persistência realista** (84,1 %; kappa 0,62). O nível **AMARELO não funciona**
   (F1 5,6 %): só 1,3 % dos patamares reais caem entre 200 e 1.000 MWmed — o corte é quase sempre
   "zero ou muito".
4. **Recomendações:** (a) corrigir o viés (prever quantil acima da mediana ou calibrar), (b) rever
   ou eliminar a faixa AMARELO, (c) backtest com origem móvel em 2023–2025, (d) confirmar que as
   variáveis de entrada estão disponíveis na hora da previsão — o código de treino (`models/`) não
   está no acervo, então **vazamento de informação não pôde ser descartado**.

---

## 2. Exatidão da FlexIA

### 2.1 Respostas ponta a ponta
13 perguntas × 2 rodadas = **26 execuções**, cada uma em sessão nova. Correta = contém o valor do
gabarito (tolerância de 0,1 % a 2 %), o trecho literal esperado, ou — nas perguntas sem resposta —
admite que os dados não cobrem o pedido.

| categoria | o que mede | acertos | acurácia |
|---|---|---:|---:|
| numéricas | valor calculado por SQL direto no lake (CMO, carga, corte, geração solar, potência SIGA, frota EV, mês de pico) | 14/14 | **100 %** |
| documentos | trecho literal da fonte (Lei 14.300 art. 1º XIV, Lei 10.847, nota da EPE) | 6/6 | **100 %** |
| sem resposta nos dados | CMO de 2018 (série começa em 2020), corte solar de 2022 (começa em abr/2024), carga de 2030 | 6/6 | **100 %** |
| **total** | | **26/26** | **100 %** |

Latência por resposta (agente já aquecido): **média 12,2 s · mediana 9,3 s · p90 17,4 s ·
máxima 54,1 s** (a máxima é a pergunta de corte total, roteada ao Claude Sonnet 4.6).

### 2.2 Roteador NVIDIA Nemotron Nano 3 30B
24 perguntas rotuladas (conversa, dados, documentos, misto, fora de escopo) × 3 repetições = 72
classificações.

| métrica | resultado |
|---|---:|
| Acurácia do rótulo | **90,3 %** |
| Estabilidade (mesma rota nas 3 repetições) | 83,3 % |
| Perguntas de dados/documentos enviadas a modelo **sem ferramentas** | **0 de 72** (antes da trava: 2) |
| Classificações indevidas como fora de escopo | 1 (sem efeito: fora de escopo vai ao Haiku com ferramentas) |
| Latência | média 0,42 s · p90 0,48 s |

Matriz (linhas = rota esperada, colunas = obtida; perguntas com duas rotas aceitáveis em linhas próprias):

| esperada \ obtida | conversa | dados | documentos | misto | fora de escopo |
|---|---:|---:|---:|---:|---:|
| conversa | 9 | 0 | 0 | 0 | 0 |
| dados | 0 | 16 | 0 | 1 | 1 |
| documentos | 0 | 0 | 15 | 0 | 0 |
| misto | 0 | 5 | 0 | 4 | 0 |
| fora de escopo | 0 | 0 | 0 | 0 | 9 |
| conversa ou documentos | 3 | 0 | 0 | 0 | 0 |
| dados ou documentos | 0 | 0 | 3 | 0 | 0 |
| dados ou misto | 0 | 5 | 0 | 1 | 0 |

O erro mais comum é "misto" classificado como "dados" (5 de 9): a pergunta vai ao Claude Haiku em
vez do Sonnet, **com todas as ferramentas** — perde capacidade de raciocínio, não perde acesso a
dados ou documentos.

### 2.3 Histórico de falhas encontradas e correções
| etapa | resultado | falha | correção |
|---|---|---|---|
| teste manual | — | **Nemotron Super 3 120B inventou os incisos II–IV da Lei 14.300**, entre aspas | documentos passaram ao Claude Haiku 4.5; regra de citação literal |
| teste manual | — | afirmou "2025 até setembro" sem consultar | regra: período só após `min/max(din_instante)` |
| rodada 1 | 9/10 | aritmética: consulta deu 91.832.656 MWh, resposta disse 80,4 TWh | regra: toda conta e conversão no SQL |
| rodada 2 | 9/10 | filtrou `tipo=publicacoes` e perdeu a notícia com o número | diversidade por documento na busca |
| rodada 3 | 9/10 | limite de 2 trechos por documento cortou o inciso XIV | limite 3 |
| rodada 4 | 9/10 | mesma falha de filtro | instrução: buscar sem filtro de tipo e repetir sem filtros antes de desistir |
| rodada 5 | 9/10 | roteador marcou "frota de EV do Rio" como fora de escopo e a pergunta foi recusada | escopo explícito; fora de escopo vai ao Haiku com ferramentas |
| rodada 6 | 10/10 | — | — |
| rodadas 7–8 | **26/26** (incluindo 3 perguntas sem resposta) | — | — |
| teste do roteador | 2 de 72 iriam sem ferramentas | "Quantos veículos elétricos há no Rio?" classificada como conversa | trava: conversa só para saudação/identidade; senão Haiku com ferramentas → **0 de 72** |

Nas falhas das rodadas 2–4 a FlexIA **disse que não encontrou** o valor em vez de inventar.

### 2.4 Limites desta avaliação
- 13 perguntas é um conjunto pequeno; 100 % em 26 execuções indica consistência nesse conjunto, não
  garante o mesmo em qualquer pergunta. Recomenda-se ampliar para 50+ perguntas, cobrindo todas as
  tabelas e fontes, e repetir a cada mudança de prompt, regras, roteador ou busca.
- As rodadas 7–8 foram feitas antes da trava do roteador (2.2); a trava só envia mais perguntas a
  modelos com ferramentas, não reduz o acesso a dados.
- Latências medidas numa máquina local com o agente aquecido; no AgentCore podem variar.
