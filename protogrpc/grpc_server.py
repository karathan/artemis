import grpc
from protogrpc import service_pb2
from protogrpc import service_pb2_grpc
import _thread
from concurrent import futures
from protobuf_to_dict import protobuf_to_dict
from webapp.models import Monitor
from sqlalchemy import exc
from webapp.shared import db_session


class GrpcServer():

    def __init__(self, monitor, detector, mitigator=None):
        self.server_process = None

        self.monitor = monitor
        self.detector = detector
        self.mitigator = mitigator

    class MonitorGrpc(service_pb2_grpc.MessageListenerServicer):

        def __init__(self, detector):
            self.detector = detector

        def queryMformat(self, request, context):
            monitor_event = Monitor(protobuf_to_dict(request))

            try:
                db_session.add(monitor_event)
                db_session.commit()
            except exc.SQLAlchemyError as e:
                db_session.rollback()
                duplicate_entry_str = "(sqlite3.IntegrityError) UNIQUE constraint failed"
                if duplicate_entry_str not in str(e):
                    print(
                        'SQLAlchemy error on GRPC server inserting m-entry into db... {}'.format(e))

                return service_pb2.Empty()

            if monitor_event.type == 'A' and self.detector.flag:
                db_session.expunge(monitor_event)
                self.detector.monitor_queue.put(monitor_event)

            return service_pb2.Empty()

    def start(self):
        self.grpc_server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=10))

        service_pb2_grpc.add_MessageListenerServicer_to_server(
            GrpcServer.MonitorGrpc(self.detector),
            self.grpc_server
        )

        self.grpc_server.add_insecure_port('[::]:50051')
        _thread.start_new_thread(self.grpc_server.start, ())
        print("GRPC Server Started..")

    def stop(self):
        self.grpc_server.stop(0)
        print("GRPC Server Stopped..")
