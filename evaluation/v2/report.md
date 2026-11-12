# Avaliação da base v2 com seleção por ranking

A base contém 1.000 itens `ACTIVE` e 1.200 consultas rotuladas. O desenvolvimento usou 700 itens e 840 consultas, sendo 630 positivas e 210 negativas. O teste usou 300 itens e 360 consultas, sendo 270 positivas e 90 negativas. Todas as formulações de busca do mesmo item ficaram no mesmo grupo.

## Critério de seleção

A API devolve até `top_k` sugestões ordenadas e não aplica um limiar para decidir se houve correspondência. Por isso, a regra atual escolhe campos, método e pesos no desenvolvimento por Hit@1, MRR e Hit@5, nessa ordem. O limiar de 0,4 ficou fixo apenas para calcular métricas secundárias de classificação por par.

A grade registrada em `results/summary.json` foi examinada pelas métricas de ranking no conjunto de desenvolvimento. Ela selecionou o híbrido com `alpha=0,5` para cosseno e `beta=0,5` para Levenshtein.

## Avaliação do teste

O avaliador calculou os escores dos 108.000 pares do grupo de teste e mediu 1.080 chamadas HTTP locais pelo `TestClient`, com cinco resultados solicitados por chamada. A saída está em `test_results/`, com `execution.json`, `pairs.csv`, `latency.csv` e `summary.json`. O comando `python -m evaluation.experiment verify --dataset evaluation/v2 --criterion ranking --output evaluation/v2/test_results` confere os arquivos e recalcula as métricas e estatísticas de latência.

| Método | Precisão | Revocação | F1 | Hit@1 | Hit@3 | Hit@5 | MRR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Cosseno | 0,3418 | 0,8481 | 0,4872 | 0,8333 | 0,9222 | 0,9444 | 0,8826 |
| Levenshtein | 0,1605 | 0,4667 | 0,2389 | 0,4481 | 0,6074 | 0,6630 | 0,5492 |
| Híbrido 0,5/0,5 | 0,4481 | 0,8148 | 0,5782 | **0,8556** | **0,9259** | **0,9481** | **0,8979** |

Os valores de precisão, revocação e F1 usam o limiar diagnóstico de 0,4. Eles não determinaram a escolha dos pesos. Hit@k e MRR consideram apenas as 270 consultas com item esperado. No teste, o híbrido colocou o item esperado em primeiro lugar em 231 consultas e entre os cinco primeiros em 256.

| Método | Chamadas | Média | Mediana | Desvio padrão | P95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Cosseno | 360 | 15,437 ms | 14,702 ms | 3,148 ms | 19,952 ms |
| Levenshtein | 360 | 15,270 ms | 14,819 ms | 2,470 ms | 19,736 ms |
| Híbrido 0,5/0,5 | 360 | 15,381 ms | 14,539 ms | 2,806 ms | 20,600 ms |

Essa latência é o tempo informado pela API em chamadas locais com catálogo em memória. Ela não inclui consulta ao MySQL, rede externa nem retomada da hospedagem.

## Análise complementar com o catálogo completo

Após o teste final, as mesmas 270 consultas positivas foram ranqueadas contra os 1.000 itens `ACTIVE`, mantendo os campos e os pesos escolhidos no desenvolvimento. O TF-IDF foi ajustado ao catálogo ampliado. Os arquivos `full_catalog_sensitivity.json` e `full_catalog_ranks.csv` registram o resumo e a posição do item esperado em cada consulta. O procedimento reproduz as métricas originais a partir de `test_results/pairs.csv` antes da comparação e pode ser repetido com `python -m evaluation.full_catalog_sensitivity`.

| Método | Candidatos | Hit@1 | Hit@5 | MRR |
| --- | ---: | ---: | ---: | ---: |
| Cosseno | 300 | 0,8333 | 0,9444 | 0,8826 |
| Cosseno | 1.000 | 0,7296 | 0,8815 | 0,8040 |
| Levenshtein | 300 | 0,4481 | 0,6630 | 0,5492 |
| Levenshtein | 1.000 | 0,3259 | 0,5148 | 0,4222 |
| Híbrido | 300 | 0,8556 | 0,9481 | 0,8979 |
| Híbrido | 1.000 | 0,7370 | 0,9111 | 0,8132 |

No híbrido, Hit@1 corresponde a 231 e 199 acertos, respectivamente. Hit@5 corresponde a 256 e 246. A queda reflete a ampliação do catálogo e o reajuste dos pesos IDF. Esta análise local não substitui o teste original nem mede a qualidade com relatos reais.

## Diagnóstico por consulta da ausência de correspondência

Uma análise posterior usou o escore híbrido do primeiro candidato para classificar cada consulta como possível correspondência (escore igual ou superior ao limiar) ou sem correspondência (escore inferior). Em vez de contar centenas de pares negativos por consulta, cada consulta contribui uma única vez. Os arquivos `query_match_diagnostic.json` e `query_match_scores_test.csv` preservam o cálculo e os escores do teste. O script `python -m evaluation.query_match_diagnostic` confere os hashes dos pares originais antes de recriá-los.

| Conjunto | Limiar | Positivas acima | Positivas abaixo | Sem correspondência abaixo | Sem correspondência acima |
| --- | ---: | ---: | ---: | ---: | ---: |
| Desenvolvimento | 0,40 | 531/630 | 99/630 | 91/210 | 119/210 |
| Desenvolvimento | 0,51 | 327/630 | 303/630 | 194/210 | 16/210 |
| Teste | 0,40 | 224/270 | 46/270 | 54/90 | 36/90 |
| Teste | 0,51 | 134/270 | 136/270 | 86/90 | 4/90 |

O corte 0,51 foi escolhido apenas no desenvolvimento, em uma grade de 0 a 1 com passo de 0,01, pela maior acurácia balanceada. No teste, ele reconheceu 86 das 90 consultas sem correspondência, mas deixou 136 das 270 positivas abaixo do corte. A classificação por escore do topo não comprova que o primeiro item esteja correto. Nenhum dos dois limiares é aplicado pela API publicada. Os valores se referem ao teste com 300 candidatos, não ao catálogo completo de 1.000 itens.

## Limitações

Os textos e rótulos são sintéticos. A validação automática confirmou estrutura e vínculos, mas não substitui a revisão semântica individual de todas as consultas. A análise complementar do catálogo completo considera apenas o ranqueamento de consultas positivas. O diagnóstico de ausência de correspondência usa somente os 300 candidatos do teste original. A medição de latência não inclui MySQL remoto, rede ou disponibilidade da hospedagem. A carga local do MySQL foi conferida separadamente, com 1.000 itens `ACTIVE`, seis `RETURNED` e quatro `ARCHIVED`. Três buscas pela API local confirmaram que itens inativos relacionados não apareceram entre as sugestões.
