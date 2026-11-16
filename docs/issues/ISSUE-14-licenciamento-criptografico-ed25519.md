# ISSUE-14: Sistema de Licenciamento Criptográfico Autônomo (Ed25519)

**Ordem de Execução:** 14º  
**Status:** Pronta para Início  
**Dependência:** Nenhuma  
**Módulos a Criar:** `licenciamento/validador.py`, `licenciamento/hardware_id.py`, `ferramentas/emissor_licenca.py`.  
**Referência de Base:** Arquitetura de licenciamento assimétrico de `c:\Users\flavi\Desktop\CNC CAM C++\tools\license_tool\`.

---

## 1. Motivação Comercial

Para comercializar o software sob modelo de **mensalidade (SaaS)** ou **licença perpétua**, é indispensável um sistema de proteção que impeça:
- Cópias piratas e redistribuição não autorizada.
- Execução em mais computadores do que o contratado.
- Criação de seriais fraudulentos por engenharia reversa.

---

## 2. Requisitos Técnicos

### 2.1. Identificação de Hardware Inviolável (*Machine ID*)
O módulo `hardware_id.py` coleta atributos físicos imutáveis da máquina:
1. UUID da Placa-Mãe (via Win32 API / WMI `csproduct`).
2. Número de Série do Volume do disco principal `C:` (`GetVolumeInformationW`).
3. Endereço MAC da placa de rede primária.
* Os dados são combinados e processados por um hash criptográfico (Blake2b / SHA-256) gerando um código amigável:  
  `CV-9A4F-28B1-0C7D`

### 2.2. Assinatura Digital Assimétrica (Curva Ed25519)
- O desenvolvedor possui a **Chave Privada Mestra** (mantida em sigilo no servidor).
- O aplicativo cliente embutido contém apenas a **Chave Pública Mestra**.
- O arquivo de licença (`licenca.lic`) contém os dados em JSON e a assinatura criptográfica Ed25519 de 64 bytes:
  ```json
  {
    "cliente": "Grafica Express Ltda",
    "machine_id": "CV-9A4F-28B1-0C7D",
    "valido_ate": "2026-12-31T23:59:59Z",
    "modulos": ["nesting", "tiling", "acabamento", "cnc", "multi_maquinas"],
    "max_impressoras": 5,
    "tipo": "SAAS_MENSAL"
  }
  ```

### 2.3. Validação Contra Adiantamento de Relógio
- O validador armazena o último timestamp de execução em um registro protegido. Se o relógio do Windows for atrasado intencionalmente pelo usuário para tentar burlar a expiração, o aplicativo bloqueia e acusa inconsistência temporal.
- Verificação de horário seguro via servidores de hora NTP na inicialização (quando conectado à internet).

### 2.4. Modos de Operação
- **Licenciado:** Todos os recursos liberados.
- **Trial (14 dias):** Todos os recursos liberados para teste em novos clientes.
- **Demo / Expirado:** Permite usar a montagem na tela, mas adiciona uma marca d'água transversal ("MODO DEMONSTRAÇÃO") na folha PDF exportada.

---

## 3. Critérios de Aceite

1. Uma licença gerada para o Computador A deve ser rejeitada com aviso claro se for copiada para o Computador B.
2. Nenhuma biblioteca externa restritiva pode ser usada (usar implementação criptográfica permissiva pura ou C-ABI).
3. A ferramenta interna de emissão de licenças (`emissor_licenca.py`) deve gerar arquivos `.lic` em 1 clique para a equipe comercial.
