# Avaliação

Os dados e resultados históricos estão em `evaluation/v1`. O novo conjunto de itens, consultas e SQL de substituição está em `evaluation/v2`; veja `evaluation/v2/README.md`. Os comandos de experimento final abaixo ainda se referem à v1.

O piloto pertence somente a `pilot_development`. O avaliador valida os dados com `evaluation.validate`, seleciona itens e consultas desse split e exporta uma linha por par consulta--candidato. Não acessa MySQL.

Para uma nova execução do piloto em uma pasta separada, execute:

```powershell
.\.venv\Scripts\python.exe -m evaluation.evaluate --output evaluation\pilot\ranking_results
```

O comando grava `pairs.csv`, `latency.csv` e `summary.json` na pasta indicada. Os dois escores base são calculados uma vez por par para cada configuração de campos e reutilizados nos três métodos e na grade. `pairs.csv` contém os escores da configuração selecionada e, nas colunas `alternative_*`, os da outra configuração. Qualquer escore híbrido pode ser reconstruído com `alpha * cosine_score + (1-alpha) * levenshtein_score`.

A comparação de campos usa híbrido com `alpha=0.5` e limiar diagnóstico `0.4`, fixados antes da grade. Em novas execuções, a seleção de campos, método e pesos prioriza Hit@1, MRR e Hit@5, nessa ordem. O limiar diagnóstico permanece em 0,4 e não participa da seleção. A grade ainda calcula F1, precisão e revocação sobre os pares para análise secundária. Consultas negativas participam dessas métricas de classificação, mas não dos denominadores de Hit@k e MRR.

A política `pair_f1` permanece disponível para reproduzir a avaliação histórica da v1. A grade de desenvolvimento da v2 está registrada em `evaluation/v2/results/`, e a seleção por ranking para o teste usa Hit@1, MRR e Hit@5. O avaliador de desenvolvimento usa `ranking` por padrão e recusa gravar sobre um `summary.json` existente. Para um novo conjunto, a seleção deve ser feita somente no desenvolvimento antes da avaliação do teste.

`latency.csv` registra requisições HTTP reais à aplicação com o catálogo do split, uma por consulta e método, fora da grade. O cabeçalho `X-Server-Time-Ms` mede no servidor do recebimento pela aplicação até a resposta HTTP construída. As estatísticas são média, mediana, desvio padrão populacional e P95 (interpolação linear do NumPy), em milissegundos. Esses números são do piloto em `TestClient`; o ambiente final deverá ser medido novamente na avaliação final.

O resumo registra checksums de entradas e saídas, versão Git, estado da árvore, ambiente, configuração e todas as métricas. O split `test` não é aceito no comando do piloto; a avaliação final será executada separadamente.

Para a base final, `evaluation/v1/manifest.json` fixa os IDs e checksums dos splits. O avaliador verifica o manifesto e seleciona apenas os candidatos e consultas de desenvolvimento antes de pontuar. Ao receber `--dataset evaluation/v1`, o split padrão é `development` e a saída padrão é `evaluation/v1/results`. O teste é acessado somente pelo comando da avaliação final com a configuração congelada.

Ao receber `--dataset evaluation/v2`, o mesmo comando usa `development` e a saída padrão seria `evaluation/v2/results`. Como essa pasta contém a avaliação congelada, informe uma nova pasta com `--output` para qualquer análise exploratória.

A avaliação da v2 com seleção por ranking está descrita em `evaluation/v2/report.md`. O avaliador comum `evaluation.experiment` confere os resultados do teste v2. Por exemplo:

```powershell
.\.venv\Scripts\python.exe -m evaluation.experiment verify --dataset evaluation\v2 --criterion ranking --output evaluation\v2\test_results
```

Para um novo conjunto, `evaluation.evaluate` calcula o desenvolvimento. Depois `evaluation.experiment freeze`, `run`, `latency` e `verify` usam os mesmos argumentos `--dataset`, `--criterion` (`ranking` ou `pair_f1`) e `--output`. O `freeze` registra a escolha feita apenas com o desenvolvimento. O `run` calcula os pares do teste, `latency` mede a API local e `verify` confere os CSVs e as métricas. Os comandos não sobrescrevem saídas existentes. O arquivo `evaluation.final_experiment` permanece como registro do fluxo legado da v1.

Para um futuro conjunto em `evaluation/v3`, depois de gerar `evaluation/v3/results/summary.json` no desenvolvimento:

```powershell
.\.venv\Scripts\python.exe -m evaluation.experiment freeze --dataset evaluation\v3 --criterion ranking --output evaluation\v3\test_results
.\.venv\Scripts\python.exe -m evaluation.experiment run --dataset evaluation\v3 --criterion ranking --output evaluation\v3\test_results
.\.venv\Scripts\python.exe -m evaluation.experiment latency --dataset evaluation\v3 --criterion ranking --output evaluation\v3\test_results
.\.venv\Scripts\python.exe -m evaluation.experiment verify --dataset evaluation\v3 --criterion ranking --output evaluation\v3\test_results
```

## Experimento final v1

O avaliador final usa os JSONL congelados e o manifesto como fonte dos candidatos e consultas. Não consulta MySQL; assim, os 1.000 itens carregados no schema sintético não entram todos na pontuação de um split. O desenvolvimento usa 700 candidatos e 840 consultas; o teste usa 300 candidatos e 360 consultas. A validação lê o dataset inteiro para conferir integridade, mas os escores são calculados somente entre os candidatos e consultas selecionados.

Na raiz da API, confira os artefatos congelados e execute a calibração:

```powershell
.\.venv\Scripts\python.exe -m evaluation.finalize
.\.venv\Scripts\python.exe -m evaluation.generate_load_sql
.\.venv\Scripts\python.exe -m evaluation.validate --items evaluation\v1\items.jsonl --queries evaluation\v1\queries.jsonl --no-pilot-profile
.\.venv\Scripts\python.exe -m evaluation.evaluate --dataset evaluation\v1
```

A calibração grava `evaluation/v1/results/{pairs.csv,latency.csv,summary.json}`. `pairs.csv` contém 588.000 pares; os escores de cada composição de campos são calculados uma vez e reutilizados na grade fixa. Depois de conferir o resumo, congele método, composição de campos, pesos, limiares, stopwords, checksums, versão e ambiente:

```powershell
.\.venv\Scripts\python.exe -m evaluation.final_experiment freeze
```

O comando cria `evaluation/v1/pretest_config.json` exclusivamente; ele falha se já existir configuração ou saída de teste. Verifique esse arquivo **antes** do próximo comando. O teste só aceita essa configuração e cria um diretório exclusivo antes de ler o split; uma segunda tentativa é bloqueada, inclusive se a primeira falhar e exigir auditoria.

```powershell
.\.venv\Scripts\python.exe -m evaluation.final_experiment test
.\.venv\Scripts\python.exe -m evaluation.final_report
```

O teste grava `evaluation/v1/test_results/{execution.json,pairs.csv,latency.csv,summary.json}`. São 108.000 pares e 1.080 medições HTTP, uma por consulta e método. O relatório `report.md` deriva métricas, tabelas e exemplos de erro dos arquivos brutos, sem recalibrar. Não altere os dados, a configuração ou o código de avaliação após abrir o teste. A latência usa o catálogo em memória pelo `TestClient` e mede o tempo no servidor; não é latência de MySQL ou de produção.

**Estado em 19/10/2026:** a primeira tentativa do teste foi interrompida antes da primeira medição HTTP porque o ambiente restrito no Windows bloqueou a abertura do `TestClient` em `socket.accept`. Ela deixou somente `evaluation/v1/test_results/execution.json`; preserve esse arquivo. `evaluation.diagnose_http_runtime`, usando apenas desenvolvimento, reproduziu a espera no ambiente restrito e completou 1.080 requisições em 9,09 s fora dele. A repetição técnica manteve a configuração congelada, foi executada fora dessa restrição e gravou em diretório separado. Não execute o comando `test` acima novamente sobre o diretório existente.

**Repetição técnica autorizada:** após a auditoria da primeira tentativa, a autora autorizou a execução fora do ambiente restrito, sem alterar a configuração pré-teste. A execução completa está em `evaluation/v1/test_results_retry_2`; `retry_context.json` identifica a tentativa global 2 e vincula a primeira, o manifesto pré-teste e o código original por SHA-256. A primeira pasta permanece intacta. Para reproduzir apenas as verificações e o relatório dos resultados já gravados, sem executar o teste novamente:

```powershell
.\.venv\Scripts\python.exe -m evaluation.verify_final_results
.\.venv\Scripts\python.exe -m evaluation.final_report --output evaluation\v1\test_results_retry_2
```

`evaluation.verify_final_results` confere o produto cartesiano de IDs, matriz de confusão, precisão, revocação, F1, Hit@1/3/5, MRR e estatísticas de latência diretamente dos CSVs. O relatório derivado está em `evaluation/v1/test_results_retry_2/report.md`. A execução de `evaluation.recover_final_experiment run` está bloqueada pelo diretório exclusivo da segunda tentativa.

O código atual inclui autenticação na API e pequenas correções posteriores ao experimento. O avaliador de desenvolvimento usa uma chave local de teste para medir a rota HTTP. O bloqueio de SHA-256 em `pretest_config.json` continua representando a revisão histórica: `evaluation.final_experiment test` não deve ser repetido neste checkout. `evaluation.final_report` lê a configuração e os CSVs já congelados para regenerar o relatório, enquanto `evaluation.verify_final_results` confere as métricas sem exigir os hashes do código atual.
