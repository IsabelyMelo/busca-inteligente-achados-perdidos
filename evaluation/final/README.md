# Base sintética final

Este diretório contém dois arquivos em JSON Lines:

- `items.jsonl`: 1.000 itens encontrados sintéticos, distribuídos em dez categorias;
- `queries.jsonl`: 1.200 descrições de busca rotuladas, sendo 1.000 com correspondência e 200 sem correspondência.

Os arquivos foram gerados em 13/10/2026 com `python -m evaluation.generate_synthetic_data`. O script combina objetos, cores e marcas fictícios com nomes de locais da unidade. A cor aparece no `name` de cada item, com concordância em nomes femininos e plurais. Não foram usados registros reais de achados e perdidos, dados pessoais ou acesso ao MySQL. Tentativas anteriores foram descartadas por repetição e problemas de redação; somente este conjunto final foi mantido.

A lista combina os locais selecionados da planta baixa enviada com o Restaurante universitário indicado no pedido: Biblioteca, Restaurante universitário, blocos 1, 2, 4, 5 e 10, Laboratório de informática, Auditório, Quadra, Secretaria, Teatro de Arena e Recanto.

Para validar a estrutura, execute na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe -m evaluation.validate --items evaluation\final\items.jsonl --queries evaluation\final\queries.jsonl --no-pilot-profile
```

## Aceite e divisão

Foram revisados os `item_id` 1001–2000 e os `query_id` `q-000001`–`q-001200`: 1.000 itens e 1.200 consultas, sem correções ou descartes comunicados na revisão final. O validador confere estrutura e vínculos, mas não substitui essa revisão humana.

A versão experimental `1.0.0` está identificada em `manifest.json`. Somente o campo `split` mudou nos dois JSONL aprovados. Antes da divisão, seus SHA-256 eram `2c1f7c92a12f9ed903ce7933b001690d6bf923ff3824865d8602f6931d722e8d` (itens) e `5818b5933d01cea07ea83cadd99d10f567b5a12dd9f90c93a1af5ba4250b55c3` (consultas).

O comando de divisão, executado uma vez sobre esses arquivos, foi:

```powershell
.\.venv\Scripts\python.exe -m evaluation.finalize --write
```

O script atribui o split por `reference_id`: ordena o SHA-256 de `final-v1-reference-stratified:<reference_id>` dentro de cada categoria, põe 70 das 100 referências em desenvolvimento e 30 em teste; faz o mesmo com as 200 referências negativas, em proporção 140/60. Cada consulta positiva acompanha seu item. O manifesto contém os IDs de itens e consultas de cada split, distribuições e SHA-256 dos JSONL. A divisão resultou em 700 itens e 840 consultas de desenvolvimento (700 positivas e 140 negativas) e 300 itens e 360 consultas de teste (300 positivas e 60 negativas). Cada categoria possui 70/30 itens. A interseção de `reference_id` é vazia.

Para conferir novamente os arquivos congelados, sem modificá-los:

```powershell
.\.venv\Scripts\python.exe -m evaluation.finalize
```

O avaliador confere o manifesto e seleciona apenas os candidatos e consultas do split solicitado antes de pontuar. O comando padrão usa desenvolvimento; a avaliação final requer a configuração pré-teste congelada. Qualquer alteração futura dos JSONL exige nova versão, revisão e novos checksums; não repita `--write` nos arquivos já divididos.

## Carga MySQL em `matching_development`

`matching_development` é o schema sintético usado pela API. Em 15/10/2026, ele já recebeu os 1.000 itens aprovados, com IDs 1001–2000, e as dez categorias de IDs 1–10. **Para conferir o estado atual, execute somente `verify_load.sql`; não execute `load.sql` no schema já preenchido.** As consultas rotuladas ficam apenas nos JSONL, e os splits permanecem no manifesto e no avaliador.

`load.sql` é o artefato de recriação para um schema `matching_development` existente, porém **sem tabelas**. Seu DDL foi baseado em `SHOW CREATE TABLE` das tabelas reais `category` e `item`, incluindo a chave estrangeira e as colunas `varchar(255)`, `foundOn datetime` e `status enum`. O arquivo cria as tabelas e insere dez categorias e 1.000 itens. Como `DATETIME` não armazena fuso, a hora civil `-03:00` dos JSONL é gravada sem offset. O arquivo não cria nem apaga schema, não contém consultas e não acessa o banco institucional.

Antes de uma recriação planejada, confira que `SHOW TABLES FROM matching_development;` não retorna linhas. No Workbench, abra `C:\www\busca-inteligente-achados-perdidos\evaluation\final\load.sql` em **File > Open SQL Script**, mantenha **Continue On Error** desativado e execute o arquivo inteiro. Em seguida, execute `verify_load.sql` da mesma pasta. No cliente MySQL, após conectar-se ao servidor, os comandos equivalentes são:

```sql
source C:/www/busca-inteligente-achados-perdidos/evaluation/final/load.sql
source C:/www/busca-inteligente-achados-perdidos/evaluation/final/verify_load.sql
```

`verify_load.sql` é somente leitura. Ele deve retornar 1.000 itens, 1.000 IDs distintos, todos `ACTIVE`, 700 IDs do split de desenvolvimento e 300 do split de teste, dez categorias e 100 itens por categoria. Os hashes esperados são `edb97e291cf9d31c26341af3eaa5db7f75ceb3b6ff698ee316c14004939e0f11` para `category_id:HEX(name)` e `0d7e0d98fe88788ddbb86ec006c760e617e63ff6676d50f05bf772a5b57c73b7` para `item_id:category_id`. Isso confere os IDs e a associação das categorias; a seleção lógica 700/300 continua no manifesto.

`CREATE TABLE` sem `IF NOT EXISTS` impede a repetição de `load.sql` sobre tabelas já criadas; as chaves primárias impedem IDs duplicados. Se uma carga falhar após criar as tabelas, examine e limpe apenas esse schema sintético antes de uma nova tentativa. O script não faz limpeza automática. A carga foi ensaiada em um schema descartável e o estado final de `matching_development` foi conferido em conexão independente, incluindo os hashes acima e os 1.000 candidatos lidos pelo repositório da API. O arquivo atual, com o destino `matching_development`, **não foi executado novamente** sobre o schema preenchido.

Para conferir a consistência dos SQLs e dos checksums registrados em `manifest.json`, execute na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe -m evaluation.generate_load_sql
```
