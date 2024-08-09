from collections import deque
from time import sleep, time

from config.parameter import MiddleWareParam, ObuSocketParam, VehicleSocketParam
from src.bridge._socket import ObuSocket, VehicleSocket
from src.obu.classes import *


class Middleware:
    def __init__(self) -> None:
        self.__init_data()
        self.config = MiddleWareParam

        self.comm_state = False
        self.obu_queue = deque([])
        self.proximity_bsm = {}
        self.proximity_rsu_data = {}
        
    def __init_data(self):
        self.ego_l2id = 0
        self.ego_bsm = BsmData()
        self.ego_bsm_light = BsmLightData()
        self.cim = CimData(self.ego_l2id)
        self.vehicle_data = VehicleData()
    
    def _create_post_l2id(self, l2id: int):

        self.dnm_rep = DnmResponseData(l2id)
        self.dmm = DmmData(l2id, self.vehicle_data.turn_signal)
        self.cim.sender = self.ego_l2id
        
    def unpack_msg_type(self, packet: bytes, _fmt: str = None) -> int:
        if _fmt is None:
            _fmt = self.ego_bsm.header_fmt
        magic, msg_type, crc16, packet_len = unpack(_fmt, packet[:7])
        return msg_type
    
    def delete_time_error_data(self, data):
        if type(data) == dict:
            current_timestamp = time()
            for vehicle_l2id, vehicle_data in data.items():
                vehicle_data: BsmData
                if current_timestamp - vehicle_data.timestamp > 3:
                    data.pop(vehicle_l2id)

    def set_obu_data(self, data: bytes):
        msg_type = self.ego_bsm.unpack_header(data)
        # msg_type = self.unpack_msg_type(data)
        obu_data = MSG_TYPE[msg_type](l2id = self.ego_l2id)
        obu_data.unpack_data(data)
        if msg_type == MessageType.DNM_REQUEST:
            self.receiver = obu_data.sender
            self.obu_module.put_queue_data(DnmResponseData(self.ego_l2id, self.receiver))
            self.proximity_rsu_data[MessageType.DNM_REQUEST] = obu_data
        elif msg_type == MessageType.L2ID_RESPONSE:
            self.ego_l2id = obu_data.l2id
            self.ego_bsm.l2id = self.ego_l2id
            self.cim.sender = self.ego_l2id
            self.proximity_rsu_data[MessageType.L2ID_RESPONSE] = obu_data
        elif msg_type == MessageType.BSM_NOIT or MessageType.BSM_LIGHT_NOIT:
            self.proximity_bsm[obu_data.l2id] = obu_data
        elif msg_type == MessageType.DMM_NOIT:
            print(f"Receive DMM_NOIT from OBU: {obu_data}")
            self.vehicle_module.set_dict_data(obu_data)
            self.proximity_rsu_data[MessageType.DMM_NOIT] = obu_data
        elif msg_type == MessageType.EDM_NOIT:
            print(f"Receive EDM_NOIT from OBU: {obu_data}")
            self.vehicle_module.set_dict_data(obu_data)
            self.proximity_rsu_data[MessageType.EDM_NOIT] = obu_data
            
        # 시나리오4에서 DNM Done을 수신해야 차선변경 가능
        
        
    def set_vehicle_data(self, data: dict):
        if not isinstance(data, dict):
            raise TypeError
        
        self.vehicle_data.update_data(data)
        self.update_data()

    def update_data(self):
        vehicle_data = self.vehicle_data
        vehicle_module = self.vehicle_module
        if not vehicle_module.is_connected:
            return False
        
        # vehicle_data.update_data(vehicle_module.get_data())
        self.ego_bsm.__dict__.update(vehicle_data.to_dict())
        if vehicle_data.turn_signal:
            self.ego_bsm_light.__dict__.update(vehicle_data.to_dict())

        return True
    
    def put_obu_queue(self, *argv):
        self.obu_module.send_queue.append(argv)

    def check_module_state(self)->bool:
        if not self.ego_l2id:
            self.obu_module.put_queue_data(L2idRequestData())
            self.comm_state = False
            return False
        return True

    def process(self):
        self.vehicle_module = VehicleSocket(VehicleSocketParam, self)
        self.obu_module = ObuSocket(ObuSocketParam, self)
        check_state = self.check_module_state
        _update_interval = self.config.update_interval
        put_obu_queue = self.obu_module.put_queue_data
        
        _proximity_bsm = self.proximity_bsm
        _proximity_rsu_data = self.proximity_rsu_data
        _delete_time_error_data = self.delete_time_error_data

        sync_time = time()
        while 1:
            if not check_state():
                sleep(3)
                continue

            _vehicle_data = self.vehicle_data
            if _vehicle_data.turn_signal:
                put_obu_queue(DmmData(self.ego_l2id, _vehicle_data.turn_signal))
            
            if _proximity_bsm:
                _delete_time_error_data(_proximity_bsm)
            if _proximity_rsu_data:
                _delete_time_error_data(_proximity_rsu_data)
                
            dt = time() - sync_time
            if _update_interval > dt:
                sleep(_update_interval - dt)
            sync_time = time()
            
def run_middleware():
    mw = Middleware()
    mw.process()
            
if __name__ == '__main__':
    mw = Middleware()
    mw.process()