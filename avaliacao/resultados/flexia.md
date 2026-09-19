# Resultados — FlexIA

Gerado por `avaliacao/avaliar_flexia.py`.

## Exatidão das respostas (ponta a ponta)

13 perguntas × 2 rodadas = 26 execuções. **Acurácia geral: 100.0 %** (por rodada: 100.0 %, 100.0 %).

| categoria | acertos | acurácia % |
|---|---:|---:|
| numéricas (gabarito SQL) | 14/14 | 100.0 |
| documentos (trecho literal) | 6/6 | 100.0 |
| sem resposta nos dados (deve admitir) | 6/6 | 100.0 |

Latência por resposta: média 12.2 s, mediana 9.3 s, p90 17.4 s, máxima 54.1 s.

| rodada | resultado | tempo | categoria | pergunta | esperado |
|---:|---|---:|---|---|---|
| 1 | ✅ | 10.3 s | numerica | Qual foi o CMO médio do subsistema Sudeste em 2025, em R$/MWh? | 216.047 |
| 1 | ✅ | 10.0 s | numerica | Qual foi a carga média do Nordeste em 2024, em MWmed? | 13121.6 |
| 1 | ✅ | 54.1 s | numerica | Quantos TWh de energia eólica foram cortados (curtailment) no Brasil em 2025, somando todas as razões? | 26.213 |
| 1 | ✅ | 9.4 s | numerica | Qual foi a geração solar total do SIN em 2025, em TWh, segundo o balanço de energia do ONS? | 91.833 |
| 1 | ✅ | 8.9 s | numerica | Qual a potência fiscalizada total, em GW, das usinas eólicas (EOL) em operação no cadastro SIGA da ANEEL? | 34.937 |
| 1 | ✅ | 10.6 s | numerica | Quantos veículos plug-in (BEV + PHEV) havia na cidade do Rio de Janeiro em julho de 2026? | 13233.0 |
| 1 | ✅ | 17.4 s | numerica | Em que mês de 2025 o corte eólico no Nordeste foi o maior? Responda o nome do mês. | ['outubro'] |
| 1 | ✅ | 7.4 s | documento | Segundo a Lei 14.300, o que é o Sistema de Compensação de Energia Elétrica (SCEE)? | ['empréstimo gratuito'] |
| 1 | ✅ | 6.4 s | documento | Qual lei autorizou a criação da Empresa de Pesquisa Energética (EPE)? | ['10.847'] |
| 1 | ✅ | 9.7 s | documento | Qual o potencial de resposta da demanda no Brasil estimado pela EPE no cenário de referência? | ['8,8 GW', '8.8 GW'] |
| 1 | ✅ | 8.1 s | sem_resposta | Qual foi o CMO médio do Sudeste em 2018? | admitir falta de dados |
| 1 | ✅ | 17.3 s | sem_resposta | Quanta energia solar foi cortada (constrained-off) no Brasil em 2022? | admitir falta de dados |
| 1 | ✅ | 4.1 s | sem_resposta | Qual será a carga média do Nordeste em 2030? | admitir falta de dados |
| 2 | ✅ | 8.6 s | numerica | Qual foi o CMO médio do subsistema Sudeste em 2025, em R$/MWh? | 216.047 |
| 2 | ✅ | 7.4 s | numerica | Qual foi a carga média do Nordeste em 2024, em MWmed? | 13121.6 |
| 2 | ✅ | 31.5 s | numerica | Quantos TWh de energia eólica foram cortados (curtailment) no Brasil em 2025, somando todas as razões? | 26.213 |
| 2 | ✅ | 7.8 s | numerica | Qual foi a geração solar total do SIN em 2025, em TWh, segundo o balanço de energia do ONS? | 91.833 |
| 2 | ✅ | 8.3 s | numerica | Qual a potência fiscalizada total, em GW, das usinas eólicas (EOL) em operação no cadastro SIGA da ANEEL? | 34.937 |
| 2 | ✅ | 9.3 s | numerica | Quantos veículos plug-in (BEV + PHEV) havia na cidade do Rio de Janeiro em julho de 2026? | 13233.0 |
| 2 | ✅ | 20.5 s | numerica | Em que mês de 2025 o corte eólico no Nordeste foi o maior? Responda o nome do mês. | ['outubro'] |
| 2 | ✅ | 6.9 s | documento | Segundo a Lei 14.300, o que é o Sistema de Compensação de Energia Elétrica (SCEE)? | ['empréstimo gratuito'] |
| 2 | ✅ | 6.4 s | documento | Qual lei autorizou a criação da Empresa de Pesquisa Energética (EPE)? | ['10.847'] |
| 2 | ✅ | 10.8 s | documento | Qual o potencial de resposta da demanda no Brasil estimado pela EPE no cenário de referência? | ['8,8 GW', '8.8 GW'] |
| 2 | ✅ | 8.7 s | sem_resposta | Qual foi o CMO médio do Sudeste em 2018? | admitir falta de dados |
| 2 | ✅ | 13.2 s | sem_resposta | Quanta energia solar foi cortada (constrained-off) no Brasil em 2022? | admitir falta de dados |
| 2 | ✅ | 4.2 s | sem_resposta | Qual será a carga média do Nordeste em 2030? | admitir falta de dados |

## Roteador NVIDIA Nemotron Nano 3 30B

24 perguntas rotuladas × 3 repetições. **Acurácia: 90.3 %**; estabilidade (mesma rota nas 3 vezes): 83.3 %; classificações indevidas como fora de escopo: 1; perguntas de dados/documentos que iriam para um modelo **sem ferramentas**: 0 de 72; latência média 0.42 s (p90 0.48 s).

Matriz (linhas = rota esperada, colunas = rota obtida):

| esperada \ obtida | conversa | dados | documentos | misto | fora_escopo |
|---|---:|---:|---:|---:|---:|
| conversa | 9 | 0 | 0 | 0 | 0 |
| dados | 0 | 16 | 0 | 1 | 1 |
| documentos | 0 | 0 | 15 | 0 | 0 |
| misto | 0 | 5 | 0 | 4 | 0 |
| fora_escopo | 0 | 0 | 0 | 0 | 9 |
| conversa/documentos | 3 | 0 | 0 | 0 | 0 |
| dados/documentos | 0 | 0 | 3 | 0 | 0 |
| dados/misto | 0 | 5 | 0 | 1 | 0 |

| pergunta | aceitas | obtidas |
|---|---|---|
| Oi, tudo bem? | conversa | conversa, conversa, conversa |
| Obrigado pela ajuda! | conversa | conversa, conversa, conversa |
| Qual é o seu nome? | conversa | conversa, conversa, conversa |
| O que você consegue fazer? | conversa, documentos | conversa, conversa, conversa |
| Qual foi o CMO médio do Sudeste em 2025? | dados | dados, dados, dados |
| Quantos MW de capacidade solar existem na Bahia? | dados | dados, dados, dados |
| Qual foi a geração eólica do Nordeste em agosto de 2026? | dados | dados, dados, dados |
| Quantos veículos elétricos há no Rio de Janeiro? ⚠️ | dados | dados, misto, dados |
| Qual a tarifa residencial da Light? | dados, documentos | documentos, documentos, documentos |
| Qual a carga do SIN ontem às 18h? | dados | dados, dados, dados |
| O que a Lei 14.300 diz sobre compensação de energia? | documentos | documentos, documentos, documentos |
| Quais as últimas notícias da CCEE? | documentos | documentos, documentos, documentos |
| O que é o PRODIST? | documentos | documentos, documentos, documentos |
| Qual lei criou a ANEEL? | documentos | documentos, documentos, documentos |
| O que a EPE publicou sobre resposta da demanda? | documentos | documentos, documentos, documentos |
| Compare o corte eólico do Nordeste em 2024 e 2025 e explique as causas regulatórias | misto | misto, misto, misto |
| O corte de energia aumentou depois das novas regras de ressarcimento? Mostre os números. ⚠️ | misto | dados, dados, dados |
| Quanto foi cortado em 2025 e o que o MME está fazendo sobre isso? ⚠️ | misto | dados, dados, misto |
| Quem ganhou a copa de 2022? | fora_escopo | fora_escopo, fora_escopo, fora_escopo |
| Me passe uma receita de bolo de cenoura | fora_escopo | fora_escopo, fora_escopo, fora_escopo |
| Qual a capital da Austrália? | fora_escopo | fora_escopo, fora_escopo, fora_escopo |
| Qual foi a evolução mensal do CMO do Nordeste em 2025 e em quais meses ficou acima de 300 R$/MWh? | dados, misto | dados, dados, dados |
| Quais usinas eólicas tiveram mais corte em 2025? ⚠️ | dados | dados, dados, fora_escopo |
| Existe relação entre vento forte e corte eólico no Nordeste? | dados, misto | dados, misto, dados |
