# Avaliação

O piloto pertence somente a `pilot_development`. O avaliador valida os dados com `evaluation.validate`, seleciona itens e consultas desse split e exporta uma linha por par consulta--candidato. Não acessa MySQL.

Na raiz da API, execute:

```powershell
.\.venv\Scripts\python.exe -m evaluation.evaluate
```

O comando grava `evaluation/results/pilot-v0.1.0/pairs.csv`, `latency.csv` e `summary.json`. Os dois escores base são calculados uma vez por par para cada configuração de campos e reutilizados nos três métodos e na grade. `pairs.csv` contém os escores da configuração selecionada e, nas colunas `alternative_*`, os da outra configuração. Qualquer escore híbrido pode ser reconstruído com `alpha * cosine_score + (1-alpha) * levenshtein_score`.

A comparação de campos usa híbrido com `alpha=0.5` e limiar `0.4`, fixados antes da grade. Seleciona a configuração por Hit@1, MRR e F1, nessa ordem; empate favorece a ausência de categoria. Depois, a grade de desenvolvimento usa pesos híbridos 0,25/0,5/0,75 e limiares 0,2/0,4/0,6. Em cada método, a seleção maximiza F1, precisão e o maior limiar, nessa ordem; os últimos empates têm ordem fixa no código. Consultas negativas participam dos pares de classificação, mas não dos denominadores de Hit@k e MRR.

`latency.csv` registra requisições HTTP reais à aplicação com o catálogo do split, uma por consulta e método, fora da grade. O cabeçalho `X-Server-Time-Ms` mede no servidor do recebimento pela aplicação até a resposta HTTP construída. As estatísticas são média, mediana, desvio padrão populacional e P95 (interpolação linear do NumPy), em milissegundos. Esses números são do piloto em `TestClient`; o ambiente final deverá ser medido novamente em E07.

O resumo registra checksums de entradas e saídas, versão Git, estado da árvore, ambiente, configuração e todas as métricas. O split `test` não é aceito neste comando de E04; a abertura do teste final pertence a E07.
