# ADR 0001: Agora será local, Markdown-first y Git-native

- Estado: Aceptado
- Fecha: 2026-08-14

## Contexto

Agora debe gobernar swarms humanos y agenticos sin depender de un proveedor, LLM, IDE, metodología,
plataforma o runtime. También debe integrarse con las herramientas diarias de desarrollo y permitir
continuar el trabajo entre local, CLI, CI/CD y cloud.

El primer prototipo utilizó un kernel TypeScript con snapshot JSON. Aunque demostraba invariantes, ese
modelo convertía Agora en una aplicación de estado y duplicaba la información que debe vivir en el
repositorio.

## Decisión

Distribuir una CLI instalable y templates versionados, siguiendo el modelo de herramientas locales de
inicialización. La CLI materializa configuración personal en `~/.agora`, protocolo de proyecto en
`.agora`, adapters para el agente elegido y un branch por swarm.

Usar Markdown con front matter JSON-compatible como contrato operativo. Leer workflows, roles,
capabilities y allowed actions desde Method Packs. Usar filesystem como estado presente y Git como
historial, sincronización y superficie de revisión. No invocar directamente SDKs de LLM ni almacenar
credenciales.

## Consecuencias

El proceso es visible para humanos, portable entre agentes y recuperable sin una base de datos. Los
Method Packs pueden revisarse como código y cada ambiente puede instalar su propio adapter.

La CLI debe resolver concurrencia, migraciones de documentos y compatibilidad de templates en futuras
versiones. Markdown no reemplaza validación: el front matter conserva metadatos estructurados y los
gates siguen siendo ejecutables.

## Trabajo futuro

- Registro instalable de Method Packs e integraciones.
- Tool manifests para Jira, repositorios, CI/CD, documentación y cloud.
- Handoffs ejecutables y swarms recursivos con límites de delegación.
- Locks o leases para trabajo distribuido.
- Políticas de aprobación humana, presupuestos y permisos por ambiente.
