# Avaliação

O piloto pertence somente a `pilot_development`. O avaliador valida os dados com `evaluation.validate`, seleciona itens e consultas desse split e exporta uma linha por par consulta--candidato. Não acessa MySQL.

Na raiz da API, execute:

```powershell
.\.venv\Scripts\python.exe -m evaluation.evaluate
```

O comando grava `evaluation/pilot/results/pairs.csv`, `latency.csv` e `summary.json`. Os dois escores base são calculados uma vez por par para cada configuração de campos e reutilizados nos três métodos e na grade. `pairs.csv` contém os escores da configuração selecionada e, nas colunas `alternative_*`, os da outra configuração. Qualquer escore híbrido pode ser reconstruído com `alpha * cosine_score + (1-alpha) * levenshtein_score`.

A comparação de campos usa híbrido com `alpha=0.5` e limiar `0.4`, fixados antes da grade. Seleciona a configuração por Hit@1, MRR e F1, nessa ordem; empate favorece a ausência de categoria. Depois, a grade de desenvolvimento usa pesos híbridos 0,25/0,5/0,75 e limiares 0,2/0,4/0,6. Em cada método, a seleção maximiza F1, precisão e o maior limiar, nessa ordem; os últimos empates têm ordem fixa no código. Consultas negativas participam dos pares de classificação, mas não dos denominadores de Hit@k e MRR.

`latency.csv` registra requisições HTTP reais à aplicação com o catálogo do split, uma por consulta e método, fora da grade. O cabeçalho `X-Server-Time-Ms` mede no servidor do recebimento pela aplicação até a resposta HTTP construída. As estatísticas são média, mediana, desvio padrão populacional e P95 (interpolação linear do NumPy), em milissegundos. Esses números são do piloto em `TestClient`; o ambiente final deverá ser medido novamente na avaliação final.

O resumo registra checksums de entradas e saídas, versão Git, estado da árvore, ambiente, configuração e todas as métricas. O split `test` não é aceito no comando do piloto; a avaliação final será executada separadamente.

Para a base final, `evaluation/final/manifest.json` fixa os IDs e checksums dos splits. O avaliador verifica o manifesto e seleciona apenas os candidatos e consultas de desenvolvimento antes de pontuar. Ao receber `--dataset evaluation/final`, o split padrão é `development` e a saída padrão é `evaluation/final/results`. O teste é acessado somente pelo comando da avaliação final com a configuração congelada.

## Experimento final

O avaliador final usa os JSONL congelados e o manifesto como fonte dos candidatos e consultas. Não consulta MySQL; assim, os 1.000 itens carregados no schema sintético não entram todos na pontuação de um split. O desenvolvimento usa 700 candidatos e 840 consultas; o teste usa 300 candidatos e 360 consultas. A validação lê o dataset inteiro para conferir integridade, mas os escores são calculados somente entre os candidatos e consultas selecionados.

Na raiz da API, confira os artefatos congelados e execute a calibração:

```powershell
.\.venv\Scripts\python.exe -m evaluation.finalize
.\.venv\Scripts\python.exe -m evaluation.generate_load_sql
.\.venv\Scripts\python.exe -m evaluation.validate --items evaluation\final\items.jsonl --queries evaluation\final\queries.jsonl --no-pilot-profile
.\.venv\Scripts\python.exe -m evaluation.evaluate --dataset evaluation\final
```

A calibração grava `evaluation/final/results/{pairs.csv,latency.csv,summary.json}`. `pairs.csv` contém 588.000 pares; os escores de cada composição de campos são calculados uma vez e reutilizados na grade fixa. Depois de conferir o resumo, congele método, composição de campos, pesos, limiares, stopwords, checksums, versão e ambiente:

```powershell
.\.venv\Scripts\python.exe -m evaluation.final_experiment freeze
```

O comando cria `evaluation/final/pretest_config.json` exclusivamente; ele falha se já existir configuração ou saída de teste. Verifique esse arquivo **antes** do próximo comando. O teste só aceita essa configuração e cria um diretório exclusivo antes de ler o split; uma segunda tentativa é bloqueada, inclusive se a primeira falhar e exigir auditoria.

```powershell
.\.venv\Scripts\python.exe -m evaluation.final_experiment test
.\.venv\Scripts\python.exe -m evaluation.final_report
```

O teste grava `evaluation/final/test_results/{execution.json,pairs.csv,latency.csv,summary.json}`. São 108.000 pares e 1.080 medições HTTP, uma por consulta e método. O relatório `report.md` deriva métricas, tabelas e exemplos de erro dos arquivos brutos, sem recalibrar. Não altere os dados, a configuração ou o código de avaliação após abrir o teste. A latência usa o catálogo em memória pelo `TestClient` e mede o tempo no servidor; não é latência de MySQL ou de produção.

**Estado em 19/10/2026:** a primeira tentativa do teste foi interrompida antes da primeira medição HTTP porque o ambiente restrito no Windows bloqueou a abertura do `TestClient` em `socket.accept`. Ela deixou somente `evaluation/final/test_results/execution.json`; preserve esse arquivo. `evaluation.diagnose_http_runtime`, usando apenas desenvolvimento, reproduziu a espera no ambiente restrito e completou 1.080 requisições em 9,09 s fora dele. A repetição técnica manteve a configuração congelada, foi executada fora dessa restrição e gravou em diretório separado. Não execute o comando `test` acima novamente sobre o diretório existente.

**Repetição técnica autorizada:** após a auditoria da primeira tentativa, a autora autorizou a execução fora do ambiente restrito, sem alterar a configuração pré-teste. A execução completa está em `evaluation/final/test_results_retry_2`; `retry_context.json` identifica a tentativa global 2 e vincula a primeira, o manifesto pré-teste e o código original por SHA-256. A primeira pasta permanece intacta. Para reproduzir apenas as verificações e o relatório dos resultados já gravados, sem executar o teste novamente:

```powershell
.\.venv\Scripts\python.exe -m evaluation.verify_final_results
.\.venv\Scripts\python.exe -m evaluation.final_report --output evaluation\final\test_results_retry_2
```

`evaluation.verify_final_results` confere o produto cartesiano de IDs, matriz de confusão, precisão, revocação, F1, Hit@1/3/5, MRR e estatísticas de latência diretamente dos CSVs. O relatório derivado está em `evaluation/final/test_results_retry_2/report.md`. A execução de `evaluation.recover_final_experiment run` está bloqueada pelo diretório exclusivo da segunda tentativa.
