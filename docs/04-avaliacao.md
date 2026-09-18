# Avaliação

Duas perguntas diferentes, avaliadas separadamente:

1. **Quão precisa é uma previsão feita com dados históricos?** A única previsão existente no
   projeto é o modelo D+1 de corte energético (ENE) do Nordeste, feito pela equipe. A FlexIA
   **não faz previsões**: ela consulta dados e documentos e explica. O modelo foi avaliado aqui
   de forma independente.
2. **Quão exatas são as respostas da FlexIA?** Medido com perguntas cujo gabarito foi calculado
   direto nos dados e nos documentos.

Scripts: `avaliacao/avaliar_previsao.py` e `avaliacao/avaliar_flexia.py`.

---

## 1. Previsão D+1 de corte ENE no Nordeste (modelo da equipe)

### O que é o modelo
- Gradient boosting (`HistGradientBoostingRegressor`, perda absoluta) que prevê, para o dia
  seguinte, o corte por razão energética (ENE) no Nordeste em cada patamar de 30 min. O modelo
  aprende o **resíduo sobre a climatologia** (média histórica por mês/semana/patamar).
- Treino com dados **até 31/12/2025**; teste em **01/01 a 06/09/2026** (11.952 patamares), período
  que o modelo não viu no treino — separação temporal correta.
- Fonte: `analytics_previsao_ene_ne_2026` (colunas `real_ne`, `previsto`, `clima_ne`). O valor real
  confere com o gabarito `analytics_gabarito_ene_2026` (diferença máxima 1e-11).
- **Limite desta avaliação:** o código de treino (`models/dataset.py`, `models/treinar.py`) não está
  no acervo; só a saída. Por isso **não foi possível retreinar nem verificar vazamento de dados**
  (por exemplo, se alguma variável de entrada usa o clima observado do próprio dia previsto — o que
  em operação só estaria disponível como previsão meteorológica, menos precisa).

### Resultados (2026, fora da amostra)

Por patamar de 30 min (primeira semana excluída para permitir o comparador semanal):

| método | MAE (MWmed) | RMSE (MWmed) | viés (MWmed) | WAPE | correlação |
|---|---:|---:|---:|---:|---:|
| **modelo** | **1.309,6** | **2.813,2** | −578,5 | **58,2 %** | **0,814** |
| climatologia | 1.572,0 | 3.154,5 | −88,3 | 69,8 % | 0,748 |
| persistência (mesmo patamar, dia anterior)* | 1.527,2 | 3.377,3 | −8,5 | 67,8 % | 0,745 |
| semanal (mesmo patamar, 7 dias antes) | 1.928,8 | 4.109,0 | −28,5 | 85,7 % | 0,620 |

\* comparador otimista: ao prever D+1, o dia D ainda não terminou.

Ganho de MAE do modelo: **16,7 %** sobre a climatologia, **14,2 %** sobre a persistência,
**32,1 %** sobre o semanal. O MAE bate com o registrado pela equipe (1.298 MWmed na série completa).

Outros recortes:

| recorte | resultado |
|---|---|
| Energia do dia (MWh) | WAPE 50,9 %; correlação 0,76; MAE 27.150 MWh/dia para média real de 53.389 MWh/dia (climatologia: 33.103) |
| "Haverá corte > 500 MWmed neste patamar?" | precisão 77,2 %, revocação 76,2 %, acurácia 86,6 % (responder sempre "não" daria 71,1 %) |
| Hora de maior corte do dia acertada com tolerância de ±1 h | 69,2 % dos dias |

Por mês (MAE em MWmed):

| mês 2026 | modelo | climatologia | corte real médio |
|---|---:|---:|---:|
| jan | 1.054 | 1.423 | 1.137 |
| fev | 523 | 985 | 700 |
| mar | 1.136 | **1.026** | 1.446 |
| abr | 1.174 | **1.113** | 2.052 |
| mai | 1.484 | 1.638 | 2.752 |
| jun | 1.369 | 2.070 | 1.980 |
| jul | 1.733 | 2.148 | 3.620 |
| ago | 1.687 | 1.822 | 3.949 |
| set (até dia 6) | 2.059 | 2.333 | 2.220 |

### Interpretação
- **Como valor pontual em MW, a previsão é imprecisa:** o erro absoluto equivale a 58 % do volume
  cortado, e o modelo **subestima** sistematicamente (viés de −579 MWmed), efeito esperado da perda
  absoluta numa série com muitos zeros.
- **Como sinal de "se" e "quando", é útil:** acerta 77 % dos alertas de corte relevante, capta 76 %
  dos patamares com corte e acerta a hora de pico (±1 h) em 69 % dos dias. Isso é coerente com a
  decisão da equipe de usar um **sinal de três níveis** em vez do valor previsto.
- O ganho sobre comparadores simples é **real, mas modesto** (14–17 %), e em março e abril o modelo
  foi pior que a climatologia.

### O que falta para afirmar a precisão com segurança
1. Backtest com **origem móvel** (treinar até cada mês de 2023–2025 e prever o seguinte), em vez de
   um único período de teste.
2. Garantir que as variáveis de entrada sejam as **disponíveis na hora da previsão** (previsão
   meteorológica, não reanálise ERA5 do dia previsto).
3. Previsão **probabilística** (quantis P10/P50/P90) para quantificar a incerteza por patamar.
4. Recuperar o código de treino (`models/`) para versioná-lo junto com este repositório.

---

## 2. Exatidão das respostas da FlexIA

### Método
10 perguntas: 7 numéricas com gabarito calculado por SQL direto no lake local e 3 de documentos com
trecho literal esperado (Lei 14.300, Lei 10.847, nota da EPE). Cada pergunta roda numa sessão nova;
a resposta é correta se contém o valor com tolerância (0,1 % a 2 %) ou o trecho esperado.

### Resultado final (configuração atual)

**10/10 corretas, 17,6 s em média.**

| pergunta | gabarito | rota → modelo | tempo |
|---|---|---|---:|
| CMO médio do SE em 2025 | 216,05 R$/MWh | dados → Haiku 4.5 | 45,2 s* |
| Carga média do NE em 2024 | 13.121,6 MWmed | dados → Haiku 4.5 | 8,8 s |
| Corte eólico total 2025 | 26,21 TWh | dados/complexa → Sonnet 4.6 | 57,4 s |
| Geração solar do SIN em 2025 | 91,83 TWh | dados → Haiku 4.5 | 9,1 s |
| Potência eólica fiscalizada em operação (SIGA) | 34,94 GW | dados → Haiku 4.5 | 8,9 s |
| Frota plug-in do Rio, jul/2026 | 13.233 | misto → Sonnet 4.6 | 9,7 s |
| Mês de maior corte eólico no NE em 2025 | outubro | dados → Haiku 4.5 | 15,0 s |
| Definição do SCEE (Lei 14.300) | "empréstimo gratuito" (art. 1º, XIV) | documentos → Haiku 4.5 | 6,6 s |
| Lei que autorizou a criação da EPE | 10.847 | documentos → Haiku 4.5 | 5,7 s |
| Potencial de resposta da demanda (EPE) | 8,8 GW | dados → Haiku 4.5 | 9,2 s |

\* inclui a inicialização do DuckDB no processo de teste; no agente implantado isso ocorre no
aquecimento, antes da primeira pergunta.

### Histórico: falhas encontradas e correções
Cada rodada anterior teve uma falha diferente; todas foram diagnosticadas e corrigidas:

| rodada | resultado | falha | correção |
|---|---|---|---|
| teste manual | — | **Nemotron Super 3 120B inventou os incisos II–IV da Lei 14.300**, entre aspas | documentos passaram ao Claude Haiku 4.5 (transcreveu o texto exato); regra de citação literal |
| teste manual | — | FlexIA afirmou "2025 até setembro" sem consultar | regra: período só após `min/max(din_instante)` |
| 1 | 9/10 | erro de aritmética: consulta retornou 91.832.656 MWh e o modelo escreveu 80,4 TWh | regra: toda conta e conversão no SQL |
| 2 | 9/10 | modelo filtrou `tipo=publicacoes` e não achou a notícia com o número | busca com diversidade por documento |
| 3 | 9/10 | limite de 2 trechos por documento cortou o inciso XIV da lei | limite 3 |
| 4 | 9/10 | mesma falha do filtro de tipo | instrução: começar sem filtro de tipo e repetir sem filtros antes de desistir |
| 5 | 9/10 | roteador marcou "frota de EV do Rio" como fora de escopo (2 de 6 vezes) e a pergunta foi recusada | escopo explícito no roteador; "fora_escopo" vai para o Haiku com ferramentas |
| 6 | **10/10** | — | configuração atual |

Nas falhas das rodadas 2–4, a FlexIA **disse que não encontrou** o valor em vez de inventar — o
comportamento desejado quando a busca falha.

### Limites desta avaliação
- 10 perguntas é pouco para uma taxa de acerto confiável; a configuração final rodou uma vez.
  Modelos de linguagem não são determinísticos: rodadas repetidas podem variar.
- O roteador Nemotron também varia (a mesma pergunta recebeu rotas diferentes); o desenho atual
  reduz o impacto (nenhuma rota recusa sem ferramentas), mas não elimina.
- Recomendado: ampliar para 50+ perguntas cobrindo todas as tabelas e fontes, rodar 3× por
  mudança e registrar a taxa média, e incluir perguntas **sem resposta nos dados** para medir se a
  FlexIA admite a falta de informação.
