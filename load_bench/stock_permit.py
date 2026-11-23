"""T3D CZERO permission using the red board's unchanged HID firmware.

This is ordinary host-controlled I/O, not an autonomous timeout device.
The independent hardwired stop remains necessary for supervised bench trials.
"""
from .red_board import RedBoardError


class StockPermit:
    backend="stock_hid"
    autonomous_host_loss_shutdown=False
    firmware_id=None

    def __init__(self,board):
        self.board=board
        self.initial=board.initialize_io()  # only I/O init, all outputs OFF
        self.steps=list(self.initial["live_steps"])

    @property
    def trace(self):return self.board.trace

    def renew(self):
        status=self.board.outputs(1)
        if status["state"]!=1 or status["live_steps"]!=self.steps:
            self.board.outputs(0)
            raise RedBoardError("Unexpected red-board state or axis counters changed")
        return status["ack_sequence"]

    def disarm(self):
        status=self.board.stop_io()
        if status["outputs"]!=0 or status["state"]!=0:
            raise RedBoardError("Red-board OFF was not confirmed")
        return status
