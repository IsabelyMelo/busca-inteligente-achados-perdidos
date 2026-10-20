# Resultados derivados do teste final

Fonte: `pairs.csv` (5401e5179e52a7087792bb25917da45eb84136619ce6b255f707153e4d8520cd) e `latency.csv` (4aa28dfa7d9d458ef200ff5cfdbbaf5f142cd8c8b0aee887071c38628bb9c02e).
Configuração pré-teste: `b0fcf136327fedd810e6b2688ceddf9856ef51b9442a65431e34e90c3486981f`.

## Qualidade

| Método | α | Limiar | Precisão | Revocação | F1 | Hit@1 | Hit@3 | Hit@5 | MRR | TP | FP | TN | FN |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cosine | 1.0 | 0.6 | 0.5207 | 0.7967 | 0.6298 | 0.8300 | 0.9000 | 0.9500 | 0.8797 | 239 | 220 | 107480 | 61 |
| levenshtein | 0.0 | 0.6 | 0.3933 | 0.4300 | 0.4108 | 0.6600 | 0.7733 | 0.8200 | 0.7375 | 129 | 199 | 107501 | 171 |
| hybrid | 0.5 | 0.6 | 0.8969 | 0.6667 | 0.7648 | 0.8567 | 0.9467 | 0.9667 | 0.9053 | 200 | 23 | 107677 | 100 |

## Latência do servidor via HTTP

| Método | N | Média (ms) | Mediana (ms) | Desvio padrão (ms) | P95 (ms) |
|---|---:|---:|---:|---:|---:|
| cosine | 360 | 6.202 | 6.053 | 0.885 | 7.486 |
| levenshtein | 360 | 6.005 | 5.955 | 0.599 | 6.961 |
| hybrid | 360 | 6.055 | 5.994 | 0.685 | 6.919 |

## Exemplos de erro do método escolhido no desenvolvimento

Método: hybrid; pesos α=0.5, β=0.5; limiar=0.6. Os exemplos abaixo foram selecionados depois da execução, sem ajuste do método.

### Correspondência fora do primeiro resultado

- `q-000908` (hard): posição esperada 35, item esperado `1908`, primeiro item `1980`; descrição: “Era sombrinha com pequena marca verde; deixei no Bloco 2.”.
- `q-000460` (hard): posição esperada 13, item esperado `1460`, primeiro item `1187`; descrição: “Bloco de papel em tom roza com marca circular amarela, talvez no bl. 5.”.
- `q-000870` (hard): posição esperada 13, item esperado `1870`, primeiro item `1170`; descrição: “Caneleira em tom roza com sinal de desgaste, talvez no bl. 1.”.
- `q-000040` (hard): posição esperada 11, item esperado `1040`, primeiro item `1640`; descrição: “Memória usb em tom roza com ponto de tinta vermelha, talvez no bl. 2.”.
- `q-000110` (hard): posição esperada 11, item esperado `1110`, primeiro item `1510`; descrição: “Armação em tom roza com marca em forma de estrela, talvez no rec..”.

### Consulta sem correspondência acima do limiar

- `q-001106`: primeiro item `1551`, escore 0.6588; descrição: “Perdi caneta em tom preto, acabamento brilhante, com pintura em espiral dourada no Bloco 2.”.
- `q-001031`: primeiro item `1154`, escore 0.6562; descrição: “Perdi pulseira em tom verde-escuro, acabamento fosco, com lacre holográfico no Bloco 10.”.
- `q-001089`: primeiro item `1489`, escore 0.6259; descrição: “Perdi fichário em tom marrom, acabamento fosco, com faixa quadriculada lilás no Recanto.”.
- `q-001111`: primeiro item `1552`, escore 0.6026; descrição: “Perdi caneta em tom azul-marinho, acabamento brilhante, com lacre holográfico no Auditório.”.

## Limites de interpretação

A base é sintética e curada, com uma correspondência principal por consulta positiva. A classificação usa todos os pares e, por isso, é fortemente desbalanceada. A latência foi medida com TestClient local e catálogo em memória; não representa implantação remota ou consulta MySQL.
