# 2. Pergunta de pesquisa, GQM, caminho do estudo e 7 categorias

## 2.1 Pergunta de pesquisa

> **PP:** Para quem usa um servidor chave-valor como cache, **trocar o Redis pelo Valkey** (versões estáveis atuais, configuração padrão, mesma máquina e mesma carga) **muda a vazão, a latência e o consumo de recursos do serviço**?

Subperguntas:

- **PP1:** Há diferença de **vazão** (operações por segundo) entre Redis e Valkey em cargas de leitura (`GET`) e de escrita (`SET`)?
- **PP2:** Há diferença de **latência** típica (p50) e de cauda (p99)?
- **PP3:** Há diferença no **uso de memória e de CPU** do servidor sob a mesma carga?
- **PP4:** A diferença, se existir, **se mantém quando muda o modo de envio** (sem *pipeline* × com *pipeline*)?
