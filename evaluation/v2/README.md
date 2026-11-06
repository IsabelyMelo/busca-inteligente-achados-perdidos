# Conjunto de avaliação v2

Esta pasta contém a base sintética e os resultados da avaliação v2, separados dos dados e resultados históricos de `evaluation/v1`. As métricas e limitações estão em `report.md`.

## Arquivos

- `items.jsonl`: 1.000 itens encontrados, com IDs de 1 a 1.000.
- `queries.jsonl`: 1.200 consultas rotuladas, sendo 900 com item esperado e 300 sem item correspondente.
- `queries_development.jsonl` e `queries_test.jsonl`: cópias filtradas das consultas para leitura e revisão. O arquivo combinado é a entrada do validador e do avaliador.
- `insert.sql`: substitui os itens sintéticos da tabela `matching_development.item` pelos 1.000 itens `ACTIVE` da avaliação e acrescenta dez itens com status diferente. A autora executou a carga no MySQL local em 03/11/2026.

Os registros seguem o schema `evaluation/schemas/v1`: o número da versão do formato (`schema_version: 1.0`) é diferente da versão do conjunto de dados (v2). O rótulo `expected_item_id` é nulo nas buscas sem correspondência. Há 800 itens com pelo menos uma consulta positiva e 200 itens que atuam somente como candidatos distratores. Cem itens têm uma segunda formulação de consulta. Todas as buscas do mesmo item permanecem no mesmo grupo.

## Divisão e origem

O grupo de desenvolvimento possui 700 itens e 840 consultas (630 positivas, 210 negativas). O grupo de teste possui 300 itens e 360 consultas (270 positivas, 90 negativas). A divisão foi feita por referência de item, aproximadamente estratificada por categoria. As consultas negativas foram divididas separadamente. **Ajustes de pesos e limiares devem usar apenas desenvolvimento.**

A primeira base experimental, v1, foi produzida por script Python. Ao inspecioná-la, a autora considerou as descrições padronizadas demais e solicitou ao Codex uma nova geração com escolhas pseudoaleatórias mais variadas de tipos de objeto, cores, atributos, locais e formulações de busca. Essa revisão originou a v2. Vinte buscas iniciais partem de exemplos fornecidos pela autora e receberam itens sintéticos correspondentes. Os demais textos foram montados com semente fixa para a escolha de tipos de objeto, cores, marcas, condições, locais e formas de escrever a busca, com revisão de amostras. As descrições dos itens e as consultas não são relatos reais. A geração usa vocabulário e estruturas predefinidos, embora com mais variação que o conjunto v1. Portanto, ainda pode favorecer algumas palavras ou formas de consulta. A validação automática confirma formato, unicidade e vínculos, mas **não equivale a uma revisão semântica humana de todos os 1.200 rótulos**. Antes de apresentar resultados como avaliação final do TCC, convém revisar especialmente consultas genéricas e casos sem correspondência.

Para validar a estrutura na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe -m evaluation.validate --items evaluation\v2\items.jsonl --queries evaluation\v2\queries.jsonl --no-pilot-profile
```

O avaliador usa desenvolvimento por padrão. Os resultados em `results/` contêm a grade de configurações calculada nesse conjunto e estão congelados. A seleção para o teste prioriza Hit@1, MRR e Hit@5.

Em `results/summary.json`, `grid.selected` reflete a política de seleção registrada no resumo de desenvolvimento. A configuração usada no teste foi extraída de `grid.results` pela política `ranking` e consta em `test_results/summary.json`. A grade e os CSVs de desenvolvimento não foram alterados.

Para repetir a análise de desenvolvimento em uma pasta nova:

```powershell
.\.venv\Scripts\python.exe -m evaluation.evaluate --dataset evaluation\v2 --output evaluation\v2\ranking_results
```

O fluxo histórico de `evaluation.final_experiment` continua específico da v1. Os resultados do teste v2 com os pesos escolhidos por ranking estão em `test_results/`. O avaliador calculou os escores e as métricas e mediu a latência HTTP local com 360 chamadas por método. Para conferir os arquivos:

```powershell
.\.venv\Scripts\python.exe -m evaluation.experiment verify --dataset evaluation\v2 --criterion ranking --output evaluation\v2\test_results
```

Use apenas `verify` no diretório de resultados existente.

Para uma avaliação futura com outra base, execute `evaluation.evaluate` no desenvolvimento. Depois use `evaluation.experiment freeze`, `run`, `latency` e `verify` com `--dataset`, `--criterion` e `--output`. Os comandos recusam sobrescrever resultados existentes.

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

Confira o schema ativo e os dados que deseja preservar antes de executar esse SQL. Ele é uma **substituição** da base sintética atual, e não uma carga adicional. Os splits e rótulos permanecem apenas nos JSONL. A API lê os 1.000 itens `ACTIVE` após a carga. A avaliação por split carrega os JSONL em memória e filtra candidatos e consultas de cada grupo.
