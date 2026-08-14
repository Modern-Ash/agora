# Modelo de dominio

## Method Pack

Un Method Pack define roles requeridos, estados de trabajo, estado terminal, protocolo y política de
herramientas. Scrum y Kanban son packs instalados, editables y versionables. Un método personalizado
puede seguir el mismo contrato.

## Actor, role y assignment

Un **Actor** tiene identidad, tipo y capacidades. Sus tipos son humano, agente AI, swarm, servicio o
automatización. Un **Role** declara capacidades, tipos de actor y acciones permitidas. Un
**Assignment** vincula temporalmente ambos dentro de un swarm.

La identidad no cambia cuando el trabajo pasa de una persona a una AI o a un swarm. Cambia la
asignación y se conserva el handoff. Un swarm puede actuar como actor compuesto dentro de otro.

## Swarm

Un swarm es un equipo temporal, asociado a un objetivo, Method Pack y branch. Empieza `forming`, pasa
a `ready` cuando todos los roles requeridos están cubiertos, a `running` cuando avanza su trabajo y a
`completed` cuando todos sus work items alcanzan el estado terminal.

## Work

Un work item es un directorio Markdown con descripción, estado, criterios, artefactos y evidencia. Su
workflow se lee de `METHOD.md`; no está codificado en la integración del LLM.

Para actuar, un actor debe:

1. Estar registrado en el scope de usuario o proyecto.
2. Estar asignado a un rol del swarm.
3. Tener las capacidades y kind admitidos por ese rol.
4. Tener la acción incluida en `allowed-actions`.

## Artifact y evidence

Un artefacto es una salida durable o referencia externa: código, especificación, ticket, build,
review, aprobación o deployment. La evidencia registra un resultado verificable y su productor. El
gate terminal exige criterios satisfechos, tipos de artefacto requeridos y evidencia exitosa.

## Tool

Una tool representa una capacidad sobre el entorno diario del desarrollador: repositorio, Jira,
CI/CD, Confluence, cloud, observabilidad o comunicación. Method Pack, proyecto, role y actor restringen
su uso. Autenticación y secretos permanecen fuera de los documentos versionados.

## Environment

IDE, CLI, runner y agente cloud son ambientes de ejecución. No poseen el estado de Agora. Todos leen
y escriben el mismo protocolo en el workspace y sincronizan mediante Git.
