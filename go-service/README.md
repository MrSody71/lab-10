# go-service

A Go web service built with Gin and gorilla/websocket.

## Run

```bash
cd go-service
go run main.go
```

Server listens on **:8080**.

## Endpoints

| Method | Path   | Description                                     |
|--------|--------|-------------------------------------------------|
| GET    | /ping  | Returns `{"message":"pong","timestamp":<unix>}` |
| GET    | /users | Returns a JSON array of 3 hardcoded users       |
| POST   | /echo  | Accepts `{"text":"..."}`, returns echo + length |
| GET    | /ws    | WebSocket — broadcasts messages to all clients  |

## WebSocket

Connect with any WS client (e.g. `websocat ws://localhost:8080/ws`).  
On connect you receive:

```json
{"type":"welcome","message":"Connected to Go chat"}
```

Every message you send is broadcast to all connected clients.

## Logging middleware

Every request is logged to stdout:

```
method=GET path=/ping status=200 latency=123µs ip=127.0.0.1
```

## Graceful shutdown

Send `SIGINT` (Ctrl-C) or `SIGTERM`; the server waits up to 5 s for in-flight
requests to finish before exiting.
