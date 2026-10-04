# Schemas de avaliação v1

Os arquivos seguem JSON Schema Draft 2020-12 e descrevem registros JSON Lines. A versão do schema (`1.0`) é independente da versão de cada dataset. Alterações incompatíveis exigem um novo diretório de schema; extensões compatíveis devem preservar os campos obrigatórios.

`reference_id` identifica o objeto real ou sintético que originou o registro. Consultas positivas repetem a referência do item esperado. Consultas negativas usam uma referência sem candidato correspondente. Esse agrupamento permite que uma divisão futura mantenha todas as variações do mesmo objeto em um único split.

`expected_item_id` registra a correspondência principal prevista por H01. Conforme D02, a avaliação posterior poderá derivar todos os pares ordenados consulta--candidato: somente o par com esse item é positivo; os demais são negativos. O campo não altera a saída ranqueada da API.

O split `pilot_development` pertence exclusivamente ao desenvolvimento do protocolo. Ele não é o teste final e não pode ser promovido silenciosamente a esse papel.
