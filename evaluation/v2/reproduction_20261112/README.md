# Reexecução da avaliação v2 a partir de commit limpo

Em 12/11/2026, a avaliação foi repetida a partir do commit
`837a1c43409a80e22f9daed1b7756867e8bd7974`, com a árvore de trabalho
limpa. `development/summary.json` e `test/execution.json` registram essa revisão
e `working_tree_dirty: false`. As entradas foram os mesmos `items.jsonl` e
`queries.jsonl` da avaliação histórica.

Os pares da nova execução são idênticos, byte a byte, aos CSVs já publicados em
`../results/pairs.csv` e `../test_results/pairs.csv`. Por isso, não foram
duplicados nesta pasta. Os arquivos de latência e os resumos da nova execução
foram preservados separadamente. A latência varia entre medições e não é usada
para afirmar igualdade de desempenho temporal com a execução histórica.

As métricas dos três métodos no desenvolvimento e no teste coincidiram com as
históricas. A configuração do teste continuou sendo o híbrido com pesos 0,5/0,5
e limiar diagnóstico 0,4. O resumo histórico de desenvolvimento registra a
seleção por F1 de pares. A reexecução usou a política `ranking`, que já havia
sido usada para selecionar a configuração do teste original.

Para conferir os hashes, as métricas e os arquivos preservados, na raiz do
repositório, com as dependências instaladas:

```powershell
.\.venv\Scripts\python.exe -m evaluation.verify_clean_reproduction
```

Para repetir a execução sem sobrescrever os arquivos publicados, substitua
`$run` por um diretório novo fora do repositório:

```powershell
$run = Join-Path $env:TEMP 'tcc-v2-nova-execucao'
.\.venv\Scripts\python.exe -m evaluation.evaluate --dataset evaluation\v2 --output "$run\development" --split development --selection-policy ranking
.\.venv\Scripts\python.exe -m evaluation.experiment freeze --dataset evaluation\v2 --criterion ranking --output "$run\test"
.\.venv\Scripts\python.exe -m evaluation.experiment run --dataset evaluation\v2 --criterion ranking --output "$run\test"
.\.venv\Scripts\python.exe -m evaluation.experiment latency --dataset evaluation\v2 --criterion ranking --output "$run\test"
.\.venv\Scripts\python.exe -m evaluation.experiment verify --dataset evaluation\v2 --criterion ranking --output "$run\test"
```

O arquivo `evaluation/v2/results/summary.json` continua sendo o registro
histórico da primeira execução, com modificações locais. A reexecução limpa
confirma os pares e as métricas a partir de uma revisão versionada, sem alterar
a proveniência da execução original. A geração da base v2, feita com apoio de
IAG e revisão da autora, não tem script nem semente que reproduzam os textos
exatamente. A mensagem inicial está em `../prompt_original.txt`.
