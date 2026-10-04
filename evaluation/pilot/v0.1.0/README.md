# Dataset piloto v0.1.0

Este piloto testa o contrato experimental antes da criação da base completa. Contém 20 itens candidatos `ACTIVE` e 40 consultas sintéticas: 30 positivas e 10 sem correspondência. Todos os registros usam `pilot_development`; não existe conjunto de teste final nesta versão.

Os casos cobrem marcas e modelos, atributos exatos, sinônimos, abreviações, erros de digitação, omissões, reordenação, descrições genéricas e pistas de local. Os negativos compartilham classes e, em alguns casos, locais com itens candidatos para evitar uma amostra composta apenas por rejeições triviais.

## Arquivos

- `items.jsonl`: candidatos compatíveis com os campos lidos por `ItemRepository`;
- `queries.jsonl`: consultas rotuladas segundo D02 e H01;
- `provenance.json`: origem, ferramenta, correções, descartes e estado da revisão humana;
- `../../schemas/v1/`: contrato versionado dos registros.

## Validação

Na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe -m evaluation.validate
```

O comando verifica estrutura, tipos, limites da API, unicidade, referências positivas, coerência dos negativos, duplicatas, proveniência, cobertura mínima do piloto e ausência de `reference_id` em mais de um split. A validação estrutural não substitui a revisão semântica humana.

## Revisão e uso

A autora validou o piloto em 4 de outubro de 2026. A revisão humana está registrada como `approved` em `provenance.json`, abrangendo todas as consultas negativas e ao menos um caso de cada tipo de ruído. Ajustes futuros devem ser anotados em `corrections`; descartes devem ser preservados em `discarded_cases`, sem apagar o histórico.

Este conjunto pode orientar schema e curadoria. Ele não deve ser usado para relatar resultado final, escolher pesos ou limiar, nem ser renomeado como teste.

## Análise provisória de D03

O piloto mantém `location` e `category` separados no schema para permitir ablação posterior. Há pistas de local tanto em positivos quanto em negativos difíceis, e pares da mesma classe diferem por atributos e local. A evidência qualitativa favorece manter `location` no texto de recuperação: o campo ajuda a distinguir candidatos próximos sem determinar sozinho a correspondência. `category` é amplo e se repete em candidatos concorrentes; incluí-lo no texto pode aumentar artificialmente a semelhança de todos os itens da mesma classe.

A decisão provisória é incluir `location` e manter `category` apenas como metadado durante a primeira execução de desenvolvimento. Ela ainda deve ser verificada por comparação controlada no piloto em E04, sem consultar teste final e sem alterar pesos. A implementação atual continua intacta nesta etapa, portanto ainda concatena ambos os campos até que a decisão seja confirmada no motor de avaliação.
