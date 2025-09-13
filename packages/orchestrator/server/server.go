package server

import (
	"context"
	"errors"
	"fmt"
	"os"
	"regexp"
	"strings"
	"sync"

	"github.com/X-code-interpreter/sandbox-backend/packages/orchestrator/constants"
	"github.com/X-code-interpreter/sandbox-backend/packages/orchestrator/sandbox"
	"github.com/X-code-interpreter/sandbox-backend/packages/shared/grpc/orchestrator"
	"github.com/X-code-interpreter/sandbox-backend/packages/shared/network"
	"github.com/X-code-interpreter/sandbox-backend/packages/shared/telemetry"

	grpc_zap "github.com/grpc-ecosystem/go-grpc-middleware/logging/zap"
	"github.com/grpc-ecosystem/go-grpc-middleware/v2/interceptors/recovery"
	"github.com/shirou/gopsutil/v4/process"
	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
	"go.uber.org/zap"
	"google.golang.org/grpc"
)

// server manages sandboxes as provides grpc implmentations
//
// As one machine contains at most thousand of sandboxes,
// I think a map with a mutex is capable of handing this
// scale of data
type server struct {
	orchestrator.UnsafeSandboxServer
	orchestrator.UnsafeHostManageServer
	mu         sync.Mutex
	sandboxes  map[string]*sandbox.Sandbox
	netManager *sandbox.NetworkManager
	tracer     trace.Tracer
	metric     *serverMetric
	cfg        *OrchestratorConfig
}

// the second returned value is a cleanup function
// that needs to be called when shutdown the server.
//
// It just stop all the sandboxes
func NewSandboxGrpcServer(logger *zap.Logger, cfg *OrchestratorConfig) (*grpc.Server, func(), error) {
	grpcSrv := grpc.NewServer(
		grpc.StatsHandler(otelgrpc.NewServerHandler()),
		grpc.ChainUnaryInterceptor(
			grpc_zap.UnaryServerInterceptor(logger),
			recovery.UnaryServerInterceptor(),
		),
	)

	logger.Info("Initializing orchestrator server")
	if err := cfg.initialize(); err != nil {
		return nil, nil, fmt.Errorf("initialize orchestrator config failed: %w", err)
	}

	dns, err := network.NewDNS()
	if err != nil {
		return nil, nil, fmt.Errorf("new dns failed: %w", err)
	}

	metric, err := newServerMetric()
	if err != nil {
		return nil, nil, fmt.Errorf("new server metric failed: %w", err)
	}

	s := server{
		sandboxes:  make(map[string]*sandbox.Sandbox),
		netManager: sandbox.NewNetworkManager(dns, cfg.Subnet.IPNet),
		tracer:     otel.Tracer(constants.ServiceName),
		metric:     metric,
		cfg:        cfg,
	}

	orchestrator.RegisterSandboxServer(grpcSrv, &s)
	orchestrator.RegisterHostManageServer(grpcSrv, &s)
	return grpcSrv, func() { s.shutdown() }, nil
}

// Returned bool indicate whether sandbox already exists before insert
func (s *server) InsertSandbox(sbx *sandbox.Sandbox) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	id := sbx.SandboxID()
	_, ok := s.sandboxes[id]
	s.sandboxes[sbx.SandboxID()] = sbx
	return ok
}

// Returned bool indicate whether find the sandbox
func (s *server) GetSandbox(sandboxID string) (*sandbox.Sandbox, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	sbx, ok := s.sandboxes[sandboxID]
	return sbx, ok
}

// Returned bool indicate whether sandboxID exists
func (s *server) DelSandbox(sandboxID string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	_, ok := s.sandboxes[sandboxID]
	delete(s.sandboxes, sandboxID)
	return ok
}

func (s *server) shutdown() {
	ctx, span := s.tracer.Start(context.Background(), "server-shutdown")
	defer span.End()
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, sbx := range s.sandboxes {
		sbx.Stop(ctx, s.tracer)
	}
	for _, sbx := range s.sandboxes {
		if err := sbx.WaitAndCleanup(ctx, s.tracer); err != nil {
			// record errors during cleanup
			errMsg := fmt.Errorf("wait and cleanup for sandbox failed: %w", err)
			telemetry.ReportError(ctx, errMsg, attribute.String("sandbox.id", sbx.SandboxID()))
		}
	}

	s.netManager.Cleanup(ctx)
}

var templateIDRegex *regexp.Regexp = regexp.MustCompile(fmt.Sprintf(`/([\w-]+)/%s/`, sandbox.InstancesDirName))

// EnvID's alias is TemplateID
//
// When do not find the orphan process with sandboxID, this method will raise error.
// This method will also make sure that there is at most one process matches the sandboxID.
func getOrphanProcess(sandboxID string) (*process.Process, error) {
	var res *process.Process
	processes, err := process.Processes()
	if err != nil {
		return res, fmt.Errorf("cannot get processes on orchestrator: %w", err)
	}
	for _, process := range processes {
		cmdline, err := process.Cmdline()
		if err != nil {
			// TODO(huang-jl): return error or just continue?
			continue
		}
		if strings.HasPrefix(cmdline, "unshare") &&
			strings.Contains(cmdline, "ip netns exec") &&
			(strings.Contains(cmdline, constants.FcBinaryName) || strings.Contains(cmdline, constants.ChBinaryName)) &&
			strings.Contains(cmdline, sandboxID) {
			if res != nil {
				return nil, fmt.Errorf("find more than one process match sandbox id %s", sandboxID)
			}
			res = process
		}
	}
	if res == nil {
		return nil, fmt.Errorf("cannot find orphan process with sandbox id %s", sandboxID)
	}
	return res, nil
}

// Please make sure the process has not been killed when calling this method
func parseTemplateIdFromOrphanProcess(proc *process.Process) (string, error) {
	var res string
	cmdline, err := proc.Cmdline()
	if err != nil {
		return res, fmt.Errorf("cannot cmdline from orphan process: %w", err)
	}
	templateIDMatch := templateIDRegex.FindStringSubmatch(cmdline)
	if templateIDMatch == nil {
		return res, fmt.Errorf("cannot parse env id from orphan process (cmdline: %s)", cmdline)
	}
	res = string(templateIDMatch[1])
	return res, nil
}

func (s *server) purgeOne(ctx context.Context, sandboxInfo sandbox.SandboxInfo) error {
	var (
		finalErr  error
		sandboxID = sandboxInfo.SandboxID
	)
	// Similar to (*Sandbox).cleanupAfterFCStop()
	// 1. kill process
	err := func() error {
		proc, err := os.FindProcess(sandboxInfo.Pid)
		if err != nil {
			return fmt.Errorf("find orphan sandbox with pid %d failed: %w", sandboxInfo.Pid, err)
		}
		return proc.Kill()
	}()
	if err != nil {
		telemetry.ReportError(ctx, err, attribute.String("sandbox-id", sandboxID))
	} else {
		telemetry.ReportEvent(ctx, "killed orphan sandbox process", attribute.String("sandbox-id", sandboxID))
	}
	finalErr = errors.Join(finalErr, err)

	// 2. cleanup network
	err = func() error {
		var finalErr error
		sbxNetwork := network.NewSandboxNetwork(sandboxInfo.NetEnv, sandboxID)
		if err := sbxNetwork.DeleteNetns(); err != nil {
			telemetry.ReportError(ctx, err)
			finalErr = errors.Join(finalErr, err)
		}
		if err := sbxNetwork.DeleteHostVethDev(); err != nil {
			telemetry.ReportError(ctx, err)
			finalErr = errors.Join(finalErr, err)
		}
		if err := sbxNetwork.DeleteHostIptables(); err != nil {
			telemetry.ReportError(ctx, err)
			finalErr = errors.Join(finalErr, err)
		}
		if err := sbxNetwork.DeleteHostRoute(); err != nil {
			telemetry.ReportError(ctx, err)
			finalErr = errors.Join(finalErr, err)
		}
		if err := s.netManager.DeleteDNSEntry(sandboxID); err != nil {
			telemetry.ReportError(ctx, err)
			finalErr = errors.Join(finalErr, err)
		}
		return finalErr
	}()
	if err != nil {
		telemetry.ReportError(ctx, err, attribute.String("sandbox-id", sandboxID))
	} else {
		telemetry.ReportEvent(ctx, "cleanup network of orphan process", attribute.String("sandbox-id", sandboxID))
	}
	finalErr = errors.Join(finalErr, err)

	// 3. cleanup env
	// we only need EnvInstancePath, SocketPath, CgroupPath and PrometheusTargetPath
	err = func() error {
		cfg, err := s.NewSandboxConfig(ctx, &orchestrator.SandboxCreateRequest{
			// only this two field is enough to purge
			SandboxID:  sandboxID,
			TemplateID: sandboxInfo.TemplateID,
		})
		if err != nil {
			return fmt.Errorf("new sandbox failed: %w", err)
		}
		return cfg.CleanupFiles(ctx, s.tracer, false)
	}()
	if err != nil {
		telemetry.ReportError(ctx, err, attribute.String("sandbox-id", sandboxID))
	} else {
		telemetry.ReportEvent(ctx, "cleanup files of orphan process")
	}
	finalErr = errors.Join(finalErr, err)
	return finalErr
}
