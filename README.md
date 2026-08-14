# Agora

**Agents, Governance, Orchestration, Roles & Artifacts**

Agora es un framework local, Markdown-first y Git-native para gobernar equipos mixtos de humanos,
agentes AI, servicios, automatizaciones y otros swarms. Se instala una vez, configura el agente o LLM
elegido y materializa dentro de cada proyecto los roles, protocolos, herramientas, Method Packs,
artefactos y gates que restringen el trabajo.

Agora no es un project manager, un runtime de agentes ni un framework de prompts. Tampoco reemplaza
Jira, GitHub, CI/CD, Confluence o la nube. Instala una capa portable de gobernanza sobre esos entornos
y conserva su proceso en archivos revisables y branches Git.

> Estado: MVP experimental. Los contratos Markdown pueden evolucionar antes de la primera versión
> estable.

## Modelo de instalación

```text
Distribución de Agora
  CLI + templates + Method Packs + adapters

~/.agora/
  config.md             Defaults de integración, proveedor, modelo y método
  actors/*.md           Actores reutilizables del usuario

<proyecto>/.agora/
  project.md            Configuración efectiva del proyecto
  constitution.md       Principios y restricciones locales
  PROTOCOL.md           Protocolo común de colaboración
  commands/*.md         Comandos portables para agentes
  methods/              Scrum y Kanban
  actors/               Actores propios del proyecto
  tools/                 Política de herramientas e integraciones
  artifacts/             Catálogo de artefactos
  swarms/                Estado durable del trabajo
```

La precedencia es:

```text
defaults de Agora < ~/.agora < .agora del proyecto < configuración del swarm
```

## Instalación desde este repositorio

Requiere Node.js 20 o posterior.

```bash
npm install
npm run build
npm link
agora --help
```

Sin instalar globalmente se puede usar `npm run agora -- <comando>` desde este repositorio.

## Configuración e inicialización

```bash
agora configure \
  --integration codex \
  --provider openai \
  --model configured-by-codex \
  --default-method scrum

cd mi-proyecto
agora init
agora doctor
```

Integraciones iniciales:

- `codex`: instala skills en `.agents/skills/agora-*/SKILL.md`.
- `claude`: instala comandos en `.claude/commands/agora.*.md`.
- `generic`: mantiene los comandos portables en `.agora/commands`.

El proveedor y modelo se persisten como selección de entorno. Este MVP no invoca directamente una
API de LLM ni almacena credenciales.

## Actores y swarms

Los actores pueden ser `human`, `ai-agent`, `swarm`, `service` o `automation`. Un Method Pack decide
qué tipos, capacidades y acciones admite cada rol.

```bash
agora actor add --scope user \
  --id owner --name "Product Owner" --kind human \
  --capability backlog-management --capability acceptance

agora actor add --id facilitator --name "AI Facilitator" --kind ai-agent \
  --capability facilitation --capability governance

agora actor add --id delivery-swarm --name "Delivery Swarm" --kind swarm \
  --capability implementation

agora swarm create --id payments --objective "Deliver governed payment changes"
agora swarm assign --swarm payments --role product-owner --actor user:owner
agora swarm assign --swarm payments --role scrum-master --actor facilitator
agora swarm assign --swarm payments --role developer --actor delivery-swarm
```

En un repositorio Git, `swarm create` crea por defecto `agora/<swarm-id>`. Use `--no-branch` para
conservar el branch actual. `--project <path>` permite operar un proyecto desde IDEs, runners o
ambientes cloud sin depender del directorio actual.

## Trabajo gobernado

```bash
agora work create --swarm payments --id payment-api --title "Implement payment API" \
  --by owner --criterion api-works:"The API satisfies its contract" \
  --required-artifact source-code --required-artifact test-report

agora work transition --swarm payments --work payment-api --to planned --by delivery-swarm
agora artifact add --swarm payments --work payment-api \
  --kind source-code --uri repo://src/payment.ts --by delivery-swarm
agora evidence add --swarm payments --work payment-api \
  --type test-run --result success --artifact repo://src/payment.ts --by facilitator
agora work criterion-satisfy --swarm payments --work payment-api \
  --criterion api-works --by owner
```

Los estados se leen del Method Pack instalado. No se pueden saltear. La transición terminal exige:

1. Todos los criterios satisfechos.
2. Todos los tipos de artefacto requeridos.
3. Al menos una evidencia exitosa.
4. Un actor asignado cuyo rol permita la acción.

## Persistencia

Cada swarm contiene manifiesto, asignaciones, interacciones, eventos, trabajo, artefactos y evidencia:

```text
.agora/swarms/payments/
  SWARM.md
  events.md
  interactions.md
  artifacts.md
  evidence.md
  work/payment-api/
    WORK.md
    events.md
    interactions.md
    artifacts.md
    evidence.md
```

El filesystem es el estado actual. Git aporta historial, branches, revisión, sincronización y
handoffs entre IDE, CLI, CI/CD y agentes cloud.

## Desarrollo

```bash
npm run check
npm run example
```

El ejemplo crea un repositorio temporal, instala Agora para Codex, registra un humano, una AI y un
swarm anidado, crea el branch, demuestra un gate fallido y completa el trabajo con evidencia.

Consulte [arquitectura](docs/architecture.md), [modelo de dominio](docs/domain-model.md),
[ADR 0001](docs/decisions/0001-initial-architecture.md) y [CONTRIBUTING.md](CONTRIBUTING.md).

## Límites actuales

- Scrum y Kanban son Method Packs iniciales, no implementaciones exhaustivas de ambas metodologías.
- No hay todavía catálogo instalable de integraciones externas ni ejecución de Jira, CI/CD o cloud.
- No se implementaron handoffs ejecutables, WIP limits, locks distribuidos ni concurrencia remota.
- Las credenciales pertenecen al entorno o secret manager; Agora solo documenta referencias.
- Los front matters aceptan deliberadamente un subconjunto JSON-compatible de YAML.

## Licencia

Apache License 2.0. Consulte [LICENSE](LICENSE).
