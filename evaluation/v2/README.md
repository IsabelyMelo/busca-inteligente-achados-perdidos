# Conjunto de avaliação v2

Esta pasta contém a base sintética e os resultados da avaliação v2, separados dos dados e resultados históricos de `evaluation/v1`. As métricas e limitações estão em `report.md`.

## Arquivos

- `items.jsonl`: 1.000 itens encontrados, com IDs de 1 a 1.000.
- `queries.jsonl`: 1.200 consultas rotuladas, sendo 900 com item esperado e 300 sem item correspondente.
- `queries_development.jsonl` e `queries_test.jsonl`: cópias filtradas das consultas para leitura e revisão. O arquivo combinado é a entrada do validador e do avaliador.
- `insert.sql`: substitui os itens sintéticos da tabela `matching_development.item` pelos 1.000 itens `ACTIVE` da avaliação e acrescenta dez itens com status diferente. A autora executou a carga no MySQL local em 03/11/2026.
- `prompt_original.txt`: mensagem inicial fornecida pela autora ao Codex para solicitar a base v2, preservada com a grafia original. A mensagem documenta a solicitação inicial, mas não registra todas as iterações e revisões posteriores.

Os registros seguem o schema `evaluation/schemas/v1`: o número da versão do formato (`schema_version: 1.0`) é diferente da versão do conjunto de dados (v2). O rótulo `expected_item_id` é nulo nas buscas sem correspondência. Há 800 itens com pelo menos uma consulta positiva e 200 itens que atuam somente como candidatos distratores. Cem itens têm uma segunda formulação de consulta. Todas as buscas do mesmo item permanecem no mesmo grupo.

## Divisão e origem

O grupo de desenvolvimento possui 700 itens e 840 consultas (630 positivas, 210 negativas). O grupo de teste possui 300 itens e 360 consultas (270 positivas, 90 negativas). A divisão foi feita por referência de item, aproximadamente estratificada por categoria. As consultas negativas foram divididas separadamente. **Ajustes de pesos e limiares devem usar apenas desenvolvimento.**

A primeira base experimental, v1, foi produzida por script Python. Ao inspecioná-la, a autora considerou as descrições padronizadas demais e solicitou ao Codex uma nova geração com maior variedade de tipos de objeto, cores, atributos, locais e formulações de busca. Essa revisão originou a v2. Vinte buscas iniciais partem de exemplos fornecidos pela autora e receberam itens sintéticos correspondentes. Os registros finais da v2 foram produzidos diretamente com apoio de IAG, sem script gerador versionado ou semente de geração documentada. Após a geração, a autora leu itens e consultas e fez correções pontuais de coerência textual e naturalidade da linguagem. Não houve registro por identificador nem contagem das alterações. As descrições dos itens e as consultas não são relatos reais. A geração usa vocabulário e estruturas predefinidos, embora com mais variação que o conjunto v1. Portanto, ainda pode favorecer algumas palavras ou formas de consulta. Entre as 1.200 consultas, 32 têm a marcação `generic` em `noise_types`; outras também podem ser ambíguas. Cada consulta positiva possui um único item de referência, de modo que candidatos alternativos plausíveis podem ser contabilizados como erros. A validação automática confirma formato, unicidade e vínculos, mas **não equivale a uma revisão semântica humana de todos os 1.200 rótulos**.

Para validar a estrutura na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe -m evaluation.validate --items evaluation\v2\items.jsonl --queries evaluation\v2\queries.jsonl --no-pilot-profile
```

O avaliador usa desenvolvimento por padrão. Os resultados em `results/` contêm a grade de configurações calculada nesse conjunto e estão congelados. A seleção para o teste prioriza Hit@1, MRR e Hit@5.

Em `results/summary.json`, `grid.selected` reflete a política de seleção registrada no resumo de desenvolvimento. A configuração usada no teste foi extraída de `grid.results` pela política `ranking` e consta em `test_results/summary.json`. A grade e os CSVs de desenvolvimento não foram alterados.

O arquivo `weight_sensitivity.json` registra uma análise complementar dos pesos sobre os pares congelados de desenvolvimento, incluindo os cinco pontos da grade original e o passo de 0,1. O script confere o SHA-256 de `results/pairs.csv` e reproduz as métricas dos pontos originais antes de gravar o resultado:

```powershell
.\.venv\Scripts\python.exe -m evaluation.weight_sensitivity
```

Nessa análise posterior, `alpha=0.6` teve Hit@1 e MRR ligeiramente maiores que `alpha=0.5` no desenvolvimento. A configuração `alpha=0.5` e os resultados de `test_results/` permanecem como os do experimento final já realizado. A análise complementar não usa os pares de teste.

O arquivo `threshold_curve.csv` registra a relação entre precisão e revocação por pares do híbrido com `alpha=0.5`, calculada sobre `results/pairs.csv` para limiares de 0 a 1 com passo de 0,01. O script confere o hash dos pares e reproduz os valores congelados no limiar 0,4. Para refazer o CSV que fundamenta a tabela do TCC:

```powershell
.\.venv\Scripts\python.exe -m evaluation.threshold_diagnostic
```

O limiar 0,4 é apenas um ponto diagnóstico de classificação por pares. A busca publicada ordena candidatos sem aplicar esse corte.

## Diagnóstico de correspondência por consulta

`query_match_diagnostic.json` e `query_match_scores_test.csv` registram uma análise posterior ao teste final com o escore híbrido do primeiro candidato de cada consulta. Uma consulta é marcada como possível correspondência quando esse escore alcança o limiar. Assim, cada uma das 360 consultas de teste contribui com uma decisão, inclusive as 90 sem item esperado. Esse diagnóstico não verifica se o candidato no topo é o item correto. Os pares e resultados congelados não são alterados.

O limiar 0,4 é apresentado por ser o corte diagnóstico já usado na classificação por pares. Separadamente, foi escolhido um limiar na grade de 0 a 1, com passo de 0,01, pela maior acurácia balanceada nas 840 consultas de desenvolvimento. Em empate, a regra prioriza maior taxa de detecção das positivas e depois o menor limiar. O valor escolhido foi 0,51 e só então aplicado às 360 consultas de teste. A escolha é exploratória e não muda a API, que continua retornando sugestões sem usar um limiar de aceitação.

| Conjunto | Limiar | Positivas acima | Positivas abaixo | Sem correspondência abaixo | Sem correspondência acima |
| --- | ---: | ---: | ---: | ---: | ---: |
| Desenvolvimento | 0,40 | 531/630 | 99/630 | 91/210 | 119/210 |
| Desenvolvimento | 0,51 | 327/630 | 303/630 | 194/210 | 16/210 |
| Teste | 0,40 | 224/270 | 46/270 | 54/90 | 36/90 |
| Teste | 0,51 | 134/270 | 136/270 | 86/90 | 4/90 |

Para reproduzir o cálculo a partir dos pares congelados:

```powershell
.\.venv\Scripts\python.exe -m evaluation.query_match_diagnostic
```

No teste, o corte 0,51 reconhece mais consultas sem correspondência, mas também rejeita mais consultas positivas. Esses números descrevem apenas o catálogo de 300 candidatos do teste sintético. A análise de catálogo completo abaixo usa apenas consultas positivas e não permite extrapolar essa decisão para os 1.000 itens da API publicada.

## Sensibilidade ao tamanho do catálogo

`full_catalog_sensitivity.json` e `full_catalog_ranks.csv` registram uma análise posterior ao teste final. As mesmas 270 consultas positivas de teste foram ranqueadas com os 1.000 itens ativos da v2, mantendo os campos e os pesos escolhidos no desenvolvimento. O TF-IDF foi ajustado ao catálogo completo, como na busca da API. Os rankings originais com 300 candidatos foram recalculados a partir dos pares congelados e conferidos contra `test_results/summary.json`. As 90 consultas sem correspondência não entram em Hit@1, Hit@5 ou MRR. Nenhum peso foi reajustado e os arquivos do teste original não foram alterados.

Para reproduzir a análise:

```powershell
.\.venv\Scripts\python.exe -m evaluation.full_catalog_sensitivity
```

| Método | Candidatos | Hit@1 | Hit@5 | MRR |
| --- | ---: | ---: | ---: | ---: |
| Cosseno | 300 | 0,8333 | 0,9444 | 0,8826 |
| Cosseno | 1.000 | 0,7296 | 0,8815 | 0,8040 |
| Levenshtein | 300 | 0,4481 | 0,6630 | 0,5492 |
| Levenshtein | 1.000 | 0,3259 | 0,5148 | 0,4222 |
| Híbrido | 300 | 0,8556 | 0,9481 | 0,8979 |
| Híbrido | 1.000 | 0,7370 | 0,9111 | 0,8132 |

No híbrido, o item esperado ficou em primeiro lugar em 231 consultas com 300 candidatos e 199 com 1.000. Ele ficou entre os cinco primeiros em 256 e 246 consultas, respectivamente. A comparação modifica tanto o número de concorrentes quanto os pesos IDF, que dependem do catálogo. Ela mede sensibilidade no conjunto sintético, sem substituir o teste original nem estimar qualidade em relatos reais. A análise é local e não mede a latência da API publicada.

## Origem e ablação das equivalências lexicais

A autora informou que as dez substituições originais vieram de sugestões do Codex após a validação da v1. A consulta exploratória `Telefone preto com capinha amarela` motivou especialmente as formas `telefone` e `capinha`. O commit `8a96839` registrou a lista em 02/11/2026, antes do commit `0385937` que registrou a v2 em 03/11/2026. A base v2 não foi avaliada antes da inclusão da lista. O histórico não permite excluir influência da lista sobre a geração posterior dos textos sintéticos. A forma `telemóvel`, ausente dos itens e consultas finais da v1 e v2, foi removida posteriormente da lista ativa. Os arquivos de análise desta seção preservam a lista original de dez formas.

`alias_occurrences.json` registra uma varredura das dez formas originais. Nenhuma ocorre nos arquivos finais da v1. Na v2, ocorrem `power bank` (11 itens, três consultas), `telefone` (cinco consultas), `capinha` (quatro consultas), `pendrive` (três consultas) e `headset` (seis itens, duas consultas). As outras cinco formas não ocorrem nesses arquivos. A presença em um arquivo não demonstra que o termo tenha motivado a inclusão da equivalência. Para refazer essa varredura histórica, use uma cópia do projeto na revisão `b526a338d02eb938c244fefd0ef1697b8c214d4` e execute:

```powershell
.\.venv\Scripts\python.exe -m evaluation.alias_provenance_scan
```

`synonym_ablation.json` registra uma análise retrospectiva no teste congelado, feita com as dez formas originais. A condição com a lista usa os pares originais, cujo hash é conferido. A condição sem a lista repete a pontuação dos mesmos 300 candidatos e 360 consultas, mantendo o híbrido com pesos 0,5/0,5 e os campos nome, descrição e local. Apenas `MATCHING_ALIASES` é desativado temporariamente. O teste final original não é sobrescrito e nenhuma configuração é escolhida novamente. Para repetir essa análise histórica, use a mesma revisão indicada acima e execute:

```powershell
.\.venv\Scripts\python.exe -m evaluation.synonym_ablation
```

| Condição | Hit@1 | Hit@5 | MRR |
| --- | ---: | ---: | ---: |
| Com equivalências | 0,8556 | 0,9481 | 0,8979 |
| Sem equivalências | 0,8481 | 0,9444 | 0,8915 |

A diferença corresponde a dois acertos no Hit@1 e um no Hit@5, entre 270 consultas positivas. A ablação mede o efeito da lista nesta base sintética. Ela não separa esse efeito de uma possível adaptação do vocabulário da base à lista já presente no código.

## Incerteza na escolha dos campos

`field_ablation_uncertainty.json` registra a comparação pareada de Hit@1 entre as composições com e sem categoria, ambas com pesos iguais para cosseno e Levenshtein. O script confere o SHA-256 de `results/pairs.csv` e reproduz as duas métricas do resumo antes de calcular as diferenças por consulta. Para refazer o resultado:

```powershell
.\.venv\Scripts\python.exe -m evaluation.field_ablation_uncertainty
```

Em 630 consultas positivas de desenvolvimento, a composição sem categoria acertou 484 primeiras posições e a composição com categoria acertou 477. Houve 14 acertos exclusivos da primeira e sete da segunda. A diferença pareada de Hit@1 foi de 1,11 ponto percentual, com intervalo de 95% por bootstrap percentil de -0,32 a 2,67 pontos percentuais (20.000 reamostragens dos 560 itens de referência, semente 20261109). Formulações do mesmo item permaneceram juntas em cada reamostragem. O intervalo inclui zero. Como a composição foi selecionada com os próprios dados de desenvolvimento, esta análise é exploratória e não valida uma vantagem em dados independentes.

Para repetir a análise de desenvolvimento em uma pasta nova:

```powershell
.\.venv\Scripts\python.exe -m evaluation.evaluate --dataset evaluation\v2 --output evaluation\v2\ranking_results
```

O fluxo histórico de `evaluation.final_experiment` continua específico da v1. Os resultados do teste v2 com os pesos escolhidos por ranking estão em `test_results/`. O avaliador calculou os escores e as métricas e mediu a latência HTTP local com 360 chamadas por método. Para conferir os arquivos:

```powershell
.\.venv\Scripts\python.exe -m evaluation.experiment verify --dataset evaluation\v2 --criterion ranking --output evaluation\v2\test_results
```

Use apenas `verify` no diretório de resultados existente.

Uma reexecução completa, feita em 12/11/2026 a partir do commit limpo `837a1c43409a80e22f9daed1b7756867e8bd7974`, está documentada em `reproduction_20261112/README.md`. Os pares e as métricas coincidiram com os resultados históricos. O script `python -m evaluation.verify_clean_reproduction` confere os arquivos dessa reexecução sem duplicar os CSVs de pares.

Para uma avaliação futura com outra base, execute `evaluation.evaluate` no desenvolvimento. Depois use `evaluation.experiment freeze`, `run`, `latency` e `verify` com `--dataset`, `--criterion` e `--output`. Os comandos recusam sobrescrever resultados existentes.

## Incerteza e testes pareados no conjunto de teste

`test_significance.json` complementa o resumo original do teste sem alterar os pares, as métricas ou a configuração congelada. `evaluation/test_significance.py` confere os hashes de `items.jsonl`, `queries.jsonl` e `test_results/pairs.csv`, reproduz as sete métricas originais dos três métodos e calcula intervalos percentis de 95% com 20.000 reamostragens (semente 20261109). A unidade de reamostragem é a referência do objeto: 240 grupos positivos e 90 sem correspondência são amostrados separadamente, mantendo juntas as duas formulações de um mesmo objeto quando existem. Para reproduzir:

```powershell
.\.venv\Scripts\python.exe -m evaluation.test_significance
```

Na comparação híbrido menos cosseno, Hit@1 diferiu em 0,0222. Nove consultas foram acertadas apenas pelo híbrido e três apenas pelo cosseno. O teste exato bilateral de McNemar deu `p=0,146`. Em Hit@5, houve uma discordância a favor do híbrido e nenhuma a favor do cosseno, com `p=1,000`. A diferença de MRR foi 0,0152, com intervalo pareado por grupos de 0,0019 a 0,0294. Os intervalos individuais das sete métricas da Tabela 1 do TCC estão no JSON.

O McNemar usa as 270 consultas positivas como pares, mas 30 são formulações adicionais de objetos já representados. Seus valores de `p` são exploratórios. O bootstrap por referência preserva essa dependência. Hit@1 e Hit@5 não mostram diferença conclusiva. O intervalo de MRR sugere uma vantagem pequena do híbrido neste teste sintético, sem estabelecer superioridade geral em relatos reais. Não foi realizado teste formal de equivalência.

## Análise dos erros de ranqueamento

`error_cases.json` reúne as 39 consultas positivas em que o item esperado não ficou em primeiro lugar no teste híbrido, das quais 14 também ficaram fora do top 5. Para cada consulta, o arquivo registra o item esperado, sua posição e os cinco primeiros candidatos. `evaluation/prepare_error_cases.py` verifica os hashes das fontes congeladas e recria o arquivo sem alterar os resultados do teste:

```powershell
.\.venv\Scripts\python.exe -m evaluation.prepare_error_cases
```

`error_review.csv` registra uma categoria principal e a observação que fundamentou a classificação exploratória de cada caso. A revisão foi auxiliada pelo Codex e as categorias não representam causas comprovadas. Uma consulta pode ter mais de um fator. São 21 casos de variação do nome do objeto, sete de variação na descrição do atributo, cinco de descrição pouco específica, três de grafia ou contexto da consulta e três de atributo distintivo pouco aproveitado. Respectivamente, oito, três, um, dois e zero desses casos ficaram fora do top 5. Nenhum erro de rótulo foi confirmado. O caso `q-000411` tem rótulo potencialmente ambíguo, pois a descrição também é compatível com o item colocado em primeiro lugar.

## Perfil de latência por etapa

`evaluation/profile_search_latency.py` mede a busca direta no computador local, separando leitura do repositório, normalização dos textos, ajuste da matriz TF-IDF, transformação da consulta, cosseno e Levenshtein. Ele usa a mesma descrição na primeira chamada e em 12 repetições posteriores para três cenários: 300 itens em memória, 1.000 itens em memória e 1.000 itens no MySQL local. Não altera o banco nem os resultados congelados. Para recriar `latency_profile_local.json` com o MySQL local configurado:

```powershell
.\.venv\Scripts\python.exe -m evaluation.profile_search_latency --with-db
```

Na execução de 09/11/2026, as medianas totais após a primeira chamada foram 13,0 ms, 42,0 ms e 57,9 ms, respectivamente. Com 1.000 itens no MySQL local, a leitura teve mediana de 10,4 ms, a normalização de 41,5 ms e o cálculo de similaridade de 2,9 ms. O ajuste TF-IDF durou 9,3 ms na primeira chamada desse cenário e não se repetiu nas 12 seguintes. A medição não reproduz o ambiente do Render e da Aiven.

Para uma medição equivalente na API publicada **após implantar esta versão**, envie uma busca autenticada com `X-Profile-Timings: 1`. A resposta inclui `X-Search-Profile`, com tempos em milissegundos para `repository_ms`, `prepare_items_ms`, `tfidf_fit_ms`, `cosine_ms`, `ranking_ms` e `total_ms`, além de `item_count` e `tfidf_refit` quando houve novo ajuste. A rota não altera o JSON de resposta e o cabeçalho de diagnóstico só é gerado quando solicitado. Registre várias chamadas com o serviço ativo e compare as etapas com `processing_time_ms` e `X-Server-Time-Ms`. Não publique a chave de serviço nem os textos das consultas nos resultados.

`evaluation/profile_remote_search.py` automatiza sete chamadas autenticadas (uma inicial e seis posteriores) e salva apenas os tempos em `latency_profile_remote.json`. O script lê `SERVICE_API_KEY` do ambiente, sem gravá-la. Execute-o localmente após carregar a credencial apenas na sessão do terminal. A medição não é gerada automaticamente pelo deploy.

Na medição de 09/11/2026, após o deploy manual da revisão `b4e4e83`, a primeira busca levou 1.904,2 ms dentro do serviço: 1.458,5 ms no repositório, 245,6 ms na preparação dos candidatos e 133,5 ms no ajuste TF-IDF. Nas seis seguintes, a mediana da busca foi 635,4 ms, com 350,2 ms no repositório, 276,5 ms na preparação e nenhum novo ajuste TF-IDF. Os 1.000 candidatos ativos foram recebidos em todas as chamadas. O repositório agrega conexão, SQL, transferência e conversão dos registros. O perfil não mede CPU nem isola essas partes da leitura. A inferência sustentada é que o tempo remoto observado se concentrou na leitura do repositório e na preparação repetida dos textos, sem reajuste da matriz em cada chamada.

## Carga no MySQL

`insert.sql` foi preparado para o schema `matching_development` já usado pela API. Ele pressupõe as tabelas `category` e `item` existentes, com as dez categorias e IDs 1–10 da v1. Não são necessárias novas categorias. O arquivo apaga os itens atuais e insere 1.010 registros na mesma transação. Os IDs 1–1.000 são `ACTIVE` e constam em `items.jsonl`. Os IDs 1001–1010 são extras, com seis registros `RETURNED` e quatro `ARCHIVED`, sem `split` ou rótulos de avaliação. O próximo `AUTO_INCREMENT` fica em 1011. Os IDs dos itens avaliados são incluídos explicitamente para que os rótulos JSON apontem para as mesmas linhas do banco. O campo `found_on` dos JSONL inclui o fuso `-03:00`. `foundOn` no MySQL guarda a hora local sem offset.

Oito itens extras têm atributos parecidos com buscas positivas já rotuladas. Eles servem para conferir que o filtro de status da API os exclui, mesmo quando o texto é parecido:

| Item extra | Status | Busca relacionada |
| --- | --- | --- |
| 1001 | RETURNED | `q-000001` (fone JBL) |
| 1002 | RETURNED | `q-000002` (carregador branco) |
| 1003 | RETURNED | `q-000003` (notebook Dell) |
| 1004 | RETURNED | `q-000007` (mouse Logitech) |
| 1005 | RETURNED | `q-000008` (power bank Xiaomi) |
| 1006 | RETURNED | `q-000015` (mochila azul) |
| 1007 | ARCHIVED | `q-000014` (guarda-chuva cinza) |
| 1008 | ARCHIVED | `q-000020` (garrafinha verde) |

Os itens 1009 e 1010 completam os exemplos `ARCHIVED`. O repositório da API consulta apenas `status = 'ACTIVE'`. Por isso, o banco terá 1.010 linhas após a carga, mas somente 1.000 serão elegíveis para a busca. Os extras não entram na divisão desenvolvimento/teste nem nas 1.200 consultas da avaliação.

A carga local foi conferida por leitura em 03/11/2026. A tabela tinha 1.010 IDs distintos, sendo 1.000 `ACTIVE`, seis `RETURNED` e quatro `ARCHIVED`. Três buscas pela API ligada ao MySQL local, com `top_k` igual a 20, confirmaram que os itens 1001, 1002 e 1003 não apareceram nas respostas a consultas relacionadas. Os itens ativos 1, 2 e 3 apareceram entre as três primeiras opções das respectivas buscas. Essa conferência é separada das métricas da avaliação, que usam os JSONL em memória.

O teste de integração `tests/test_inactive_items.py` consulta diretamente a carga v2 no MySQL sintético, usando apenas operações de leitura. Ele confirma a distribuição dos 1.010 registros por status, verifica que o repositório retorna exatamente os IDs 1–1.000 e faz dez buscas autenticadas pela rota da API, uma com o texto de cada item inativo e `top_k` igual a 20. Nenhum ID de 1001 a 1010 pode aparecer nas respostas. A rota é exercitada localmente pelo cliente de testes com uma chave temporária. O teste exige que `matching_development` esteja carregado e que a conexão esteja configurada no `.env`. Em PowerShell, execute na raiz do repositório:

```powershell
$env:RUN_DB_INTEGRATION = '1'
.\.venv\Scripts\python.exe -m pytest tests\test_inactive_items.py -q
```

Confira o schema ativo e os dados que deseja preservar antes de executar esse SQL. Ele é uma **substituição** da base sintética atual, e não uma carga adicional. Os splits e rótulos permanecem apenas nos JSONL. A API lê os 1.000 itens `ACTIVE` após a carga. A avaliação por split carrega os JSONL em memória e filtra candidatos e consultas de cada grupo.
