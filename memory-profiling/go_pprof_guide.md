# Go pprof Memory Profiling Guide

## 1. Add pprof to the Go service

Open `go-service/main.go` and make two changes:

### 1a. Add the blank import

```go
import (
    // existing imports …
    _ "net/http/pprof"  // registers /debug/pprof/ handlers on DefaultServeMux
)
```

### 1b. Expose pprof on a dedicated port

`net/http/pprof` registers its handlers on `http.DefaultServeMux`, but the Gin
server uses its own mux.  The cleanest approach is to start a second HTTP server
on a separate port (e.g. 6060) so pprof is never reachable from the public
interface:

```go
// In main(), before the signal wait:
go func() {
    log.Println("pprof listening on :6060")
    if err := http.ListenAndServe(":6060", nil); err != nil {
        log.Printf("pprof server error: %v", err)
    }
}()
```

After these two changes, rebuild and restart the service:

```bash
cd go-service
go build -o go-service .
./go-service
```

---

## 2. Browse the pprof index

Open in a browser or curl:

```
http://localhost:6060/debug/pprof/
```

Available profiles:

| Profile       | URL path                         | Description                          |
|---------------|----------------------------------|--------------------------------------|
| heap          | /debug/pprof/heap                | Live heap objects                    |
| allocs        | /debug/pprof/allocs              | All past allocations                 |
| goroutine     | /debug/pprof/goroutine           | All current goroutines               |
| cpu (30 s)    | /debug/pprof/profile?seconds=30  | CPU profile (blocking call)          |
| block         | /debug/pprof/block               | Goroutine blocking events            |
| mutex         | /debug/pprof/mutex               | Mutex contention                     |

---

## 3. Capture a heap snapshot

```bash
curl -s http://localhost:6060/debug/pprof/heap > heap.prof
```

Or capture with a GC forced beforehand (cleaner numbers):

```bash
curl -s "http://localhost:6060/debug/pprof/heap?gc=1" > heap.prof
```

---

## 4. Analyse the snapshot

### Text summary (top allocators by inuse_space)

```bash
go tool pprof -text -inuse_space heap.prof
```

Sample output:

```
Showing nodes accounting for 1.5MB, 100% of 1.5MB total
      flat  flat%   sum%        cum   cum%
    1.20MB 80.00% 80.00%     1.20MB 80.00%  github.com/gin-gonic/gin.(*Engine).ServeHTTP
    0.30MB 20.00%   100%     0.30MB 20.00%  net/http.(*Transport).getConn
```

### Top allocations by count

```bash
go tool pprof -text -inuse_objects heap.prof
```

### Interactive CLI (recommended)

```bash
go tool pprof heap.prof
# Inside the REPL:
(pprof) top10
(pprof) list main.
(pprof) web          # opens SVG call graph in browser (requires graphviz)
(pprof) quit
```

### Web UI (requires Go ≥ 1.10 and graphviz)

```bash
go tool pprof -http=:8090 heap.prof
# Then open http://localhost:8090
```

---

## 5. Live heap via go_memory_profile.py

`go_memory_profile.py` (in this directory) fetches the raw pprof heap data and
parses the `# runtime/pprof` header comment that Go emits, extracting:

| Field     | Meaning                                          |
|-----------|--------------------------------------------------|
| InUse     | Bytes in live heap objects right now             |
| Alloc     | Total bytes allocated since process start        |
| Sys       | Total bytes obtained from the OS                 |

Run it while the Go service is under load:

```bash
python go_memory_profile.py
```

---

## 6. Capture a CPU profile under load

```bash
# Record 30 seconds of CPU activity while hitting the service
ab -n 50000 -c 50 http://localhost:8080/ping &
curl -s "http://localhost:6060/debug/pprof/profile?seconds=30" > cpu.prof
go tool pprof -text cpu.prof
```

---

## 7. Goroutine leak check

After load testing, check that goroutine count returns to baseline:

```bash
curl -s http://localhost:6060/debug/pprof/goroutine?debug=1
```

A steadily growing count between runs indicates a leak.
