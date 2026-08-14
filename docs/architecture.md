# Arquitectura inicial

## Propósito

Agora instala una capa local de gobernanza para agentes y humanos. El producto distribuido es una CLI
pequeña acompañada de templates Markdown. El producto materializado es el directorio `.agora` y los
adapters del agente elegido dentro del proyecto.

```text
CLI + templates
      |
      +-> ~/.agora                  configuración personal
      +-> <project>/.agora          protocolo y estado compartido
      +-> integration adapter       skills o comandos del agente
      +-> Git branch                aislamiento e historial del swarm
```

## Componentes

### CLI

`src/cli-app.ts` traduce comandos de shell a operaciones del workspace. No mantiene un servidor ni una
base de datos. `src/workspace.ts` materializa y valida documentos, capacidades, acciones, workflows y
gates. `src/markdown.ts` implementa el front matter JSON-compatible usado por el protocolo.

### Templates

`templates/project` contiene la constitución, protocolo y catálogos base. `templates/methods` aporta
Scrum y Kanban. `templates/commands` contiene instrucciones portables que los adapters transforman en
skills de Codex o comandos de otros agentes.

### Scopes

- Distribución: defaults versionados con la CLI.
- Usuario: preferencias y actores reutilizables en `~/.agora` o `$AGORA_HOME`.
- Proyecto: constitución, integración, métodos y políticas compartidas.
- Swarm: objetivo, asignaciones, branch, trabajo y evidencia.

Los scopes más específicos pueden restringir a los anteriores. No deberían ampliar silenciosamente
permisos prohibidos por un scope superior.

### Git y filesystem

Markdown es el contrato durable y el filesystem representa el estado presente. Git añade historial,
diff, revisión, sincronización y branches. No existe un snapshot JSON paralelo. Los errores dejan el
documento anterior intacto mediante reemplazo atómico.

### Adapters de ambiente

El protocolo es idéntico en IDE, CLI, CI/CD o cloud. El adapter solo decide dónde instalar las
instrucciones ejecutables:

- Codex: `.agents/skills/agora-*/SKILL.md`.
- Claude: `.claude/commands/agora.*.md`.
- Generic: `.agora/commands/*.md`.

Agregar un adapter no debe modificar Method Packs ni reglas de dominio.

## Integraciones externas

Jira, repositorios, CI/CD, Confluence, cloud y observabilidad se modelarán como tool adapters con
capabilities explícitas. Las políticas de rol decidirán qué acciones pueden invocarse. Los resultados
se convertirán en referencias de artefacto o evidencia; las credenciales nunca se copiarán a Git.

## Seguridad y concurrencia

Este slice valida actor kind, capacidades, asignación, acción permitida, transición y gate. Todavía no
implementa sandboxing, firmas, locks distribuidos, autenticación de actores ni protección ante dos
procesos escribiendo simultáneamente. Esas reglas deben agregarse sin convertir chat history o un
servicio propietario en fuente de verdad.
