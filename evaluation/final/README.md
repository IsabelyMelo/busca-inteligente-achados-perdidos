# Base sintética final

Este diretório contém dois arquivos em JSON Lines:

- `items.jsonl`: 1.000 itens encontrados sintéticos, distribuídos em dez categorias;
- `queries.jsonl`: 1.200 descrições de busca rotuladas, sendo 1.000 com correspondência e 200 sem correspondência.

Os arquivos foram gerados em 13/10/2026 com `python -m evaluation.generate_synthetic_data`. O script combina objetos, cores e marcas fictícios com nomes de locais da unidade. A cor aparece no `name` de cada item, com concordância em nomes femininos e plurais. Não foram usados registros reais de achados e perdidos, dados pessoais ou acesso ao MySQL. Tentativas anteriores foram descartadas por repetição e problemas de redação; somente este conjunto final foi mantido.

A lista combina os locais selecionados da planta baixa enviada com o Restaurante universitário indicado no pedido: Biblioteca, Restaurante universitário, blocos 1, 2, 4, 5 e 10, Laboratório de informática, Auditório, Quadra, Secretaria, Teatro de Arena e Recanto.

## Estado da revisão

Os registros ainda são rascunhos. A estrutura foi validada, mas descrições, correspondências e rótulos precisam de revisão humana antes do uso na avaliação final ou da carga em banco. Anote correções e descartes por `item_id` ou `query_id`; os arquivos não precisam ser editados durante a leitura. O campo `split` está provisoriamente como `development` em todos os registros e será definido após a revisão.

As descrições em `queries.jsonl` são entradas para avaliar a busca e não serão inseridas no banco. Apenas os itens aprovados poderão compor um futuro script SQL para um banco sintético separado.

Para validar a estrutura, execute na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe -m evaluation.validate --items evaluation\final\items.jsonl --queries evaluation\final\queries.jsonl --no-pilot-profile
```

Esse comando não faz revisão semântica nem aprova os registros.
