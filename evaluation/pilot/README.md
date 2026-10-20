# Dataset piloto

Este piloto testa o contrato experimental antes da criação da base completa. Contém 20 itens candidatos `ACTIVE` e 40 consultas sintéticas: 30 positivas e 10 sem correspondência. Todos os registros usam `pilot_development`; não existe conjunto de teste final neste diretório.

Os casos cobrem marcas e modelos, atributos exatos, sinônimos, abreviações, erros de digitação, omissões, reordenação, descrições genéricas e pistas de local. Os negativos compartilham classes e, em alguns casos, locais com itens candidatos para evitar uma amostra composta apenas por rejeições triviais.

## Arquivos

- `items.jsonl`: candidatos compatíveis com os campos lidos por `ItemRepository`;
- `queries.jsonl`: consultas rotuladas segundo D02 e H01;
- `results/`: pares, latências e resumo da execução histórica do piloto;
- `../schemas/v1/`: contrato dos registros.

O resumo histórico mantém o caminho e os checksums das entradas da execução original; mover os arquivos não recalculou os resultados.

## Validação

Na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe -m evaluation.validate
```

O comando verifica estrutura, tipos, limites da API, unicidade, referências positivas, coerência dos negativos, duplicatas, cobertura mínima do piloto e ausência de `reference_id` em mais de um split. A validação estrutural não substitui a revisão semântica humana.

## Análise

O piloto mantém `location` e `category` separados no schema para permitir ablação posterior. Há pistas de local tanto em positivos quanto em negativos difíceis, e pares da mesma classe diferem por atributos e local. A evidência qualitativa favorece manter `location` no texto de recuperação: o campo ajuda a distinguir candidatos próximos sem determinar sozinho a correspondência. `category` é amplo e se repete em candidatos concorrentes; incluí-lo no texto pode aumentar artificialmente a semelhança de todos os itens da mesma classe.

A comparação controlada do piloto avaliou `location` no texto e `category` como metadado, sem consultar o teste final. A composição adotada reúne nome, descrição e local; a categoria permanece como metadado. Os pesos foram calibrados depois, somente no desenvolvimento.
