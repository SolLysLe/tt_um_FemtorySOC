import random

import cocotb
from cocotb.triggers import ClockCycles, Timer

from riscvmodel.insn import *

from riscvmodel.regnames import x0, gp, tp, a0

pc = 0

def set_uio_in_bit(dut, bit_index, value):
    """Set a specific bit of uio_in using binary string manipulation"""
    # Get current value as binary string, replace 'x'/'z' with '0'
    current_bin = dut.uio_in.value.binstr
    # Convert to list for manipulation
    bits = list(current_bin)
    # Note: bit_index 0 is LSB? Typically bit 0 is rightmost in binary string
    # But we need to check the actual mapping
    if len(bits) > bit_index:
        bits[-(bit_index + 1)] = '1' if value else '0'
    new_bin = ''.join(bits)
    dut.uio_in.value = new_bin

async def reset(dut, latency=1, ui_in=0x80):
    # Reset
    dut._log.info(f"Reset, latency {latency}")
    dut.ena.value = 1
    dut.ui_in.value = ui_in
    
    # Set uio_in bits using direct assignment of full value
    # Since we know the initial value should be 0, just set the whole port
    # We'll create a binary string with appropriate bits set
    uio_value = 0
    # Clear bits 0, 3, 6, 7
    for bit in [0, 3, 6, 7]:
        uio_value &= ~(1 << bit)
    dut.uio_in.value = uio_value
    
    if hasattr(dut, "qspi_data_in"):
        dut.qspi_data_in.value = 0
    dut.rst_n.value = 1
    #dut.uart_rx.value = 1
    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 0
    dut.latency_cfg.value = latency
    await ClockCycles(dut.clk, 1)
    assert dut.uio_oe.value == 0
    await ClockCycles(dut.clk, 9)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 1)
    assert dut.uio_oe.value == 0b11001001

    global pc
    pc = 0

    # Should start reading flash after 2 cycles
    await ClockCycles(dut.clk, 2)
    if hasattr(dut, "qspi_data_in"):
        await start_read(dut, 0)
        await send_instr(dut, InstructionLUI(gp, 0x01000).encode())
        await send_instr(dut, InstructionADDI(gp, gp, 0x400).encode())
        await send_instr(dut, InstructionLUI(tp, 0x08000).encode())

select = None

async def start_read(dut, addr):
    global select

    if addr is None:
        select = dut.qspi_flash_select
    elif addr >= 0x1800000:
        select = dut.qspi_ram_b_select
    elif addr >= 0x1000000:
        select = dut.qspi_ram_a_select
    else:
        select = dut.qspi_flash_select
    
    # Handle select.value comparison - convert to int if needed
    select_val = int(select.value) if hasattr(select.value, 'value') else select.value
    
    flash_sel_val = int(dut.qspi_flash_select.value) if hasattr(dut.qspi_flash_select.value, 'value') else dut.qspi_flash_select.value
    ram_a_sel_val = int(dut.qspi_ram_a_select.value) if hasattr(dut.qspi_ram_a_select.value, 'value') else dut.qspi_ram_a_select.value
    ram_b_sel_val = int(dut.qspi_ram_b_select.value) if hasattr(dut.qspi_ram_b_select.value, 'value') else dut.qspi_ram_b_select.value
    clk_out_val = int(dut.qspi_clk_out.value) if hasattr(dut.qspi_clk_out.value, 'value') else dut.qspi_clk_out.value
    
    assert select_val == 0
    assert flash_sel_val == (0 if dut.qspi_flash_select == select else 1)
    assert ram_a_sel_val == (0 if dut.qspi_ram_a_select == select else 1)
    assert ram_b_sel_val == (0 if dut.qspi_ram_b_select == select else 1)
    assert clk_out_val == 0

    if dut.qspi_flash_select != select:
        # Command
        cmd = 0x0B
        data_oe_val = int(dut.qspi_data_oe.value) if hasattr(dut.qspi_data_oe.value, 'value') else dut.qspi_data_oe.value
        assert data_oe_val == 0xF    # Command
        for i in range(2):
            await ClockCycles(dut.clk, 1, False)
            select_val = int(select.value) if hasattr(select.value, 'value') else select.value
            assert select_val == 0
            clk_out_val = int(dut.qspi_clk_out.value) if hasattr(dut.qspi_clk_out.value, 'value') else dut.qspi_clk_out.value
            assert clk_out_val == 1
            data_out_val = int(dut.qspi_data_out.value) if hasattr(dut.qspi_data_out.value, 'value') else dut.qspi_data_out.value
            assert data_out_val == (cmd & 0xF0) >> 4
            data_oe_val = int(dut.qspi_data_oe.value) if hasattr(dut.qspi_data_oe.value, 'value') else dut.qspi_data_oe.value
            assert data_oe_val == 0xF
            cmd <<= 4
            await ClockCycles(dut.clk, 1, False)
            select_val = int(select.value) if hasattr(select.value, 'value') else select.value
            assert select_val == 0
            clk_out_val = int(dut.qspi_clk_out.value) if hasattr(dut.qspi_clk_out.value, 'value') else dut.qspi_clk_out.value
            assert clk_out_val == 0

    # Address
    data_oe_val = int(dut.qspi_data_oe.value) if hasattr(dut.qspi_data_oe.value, 'value') else dut.qspi_data_oe.value
    assert data_oe_val == 0xF
    for i in range(6):
        await ClockCycles(dut.clk, 1, False)
        select_val = int(select.value) if hasattr(select.value, 'value') else select.value
        assert select_val == 0
        clk_out_val = int(dut.qspi_clk_out.value) if hasattr(dut.qspi_clk_out.value, 'value') else dut.qspi_clk_out.value
        assert clk_out_val == 1
        if addr is not None:
            data_out_val = int(dut.qspi_data_out.value) if hasattr(dut.qspi_data_out.value, 'value') else dut.qspi_data_out.value
            assert data_out_val == (addr >> (20 - i * 4)) & 0xF
        data_oe_val = int(dut.qspi_data_oe.value) if hasattr(dut.qspi_data_oe.value, 'value') else dut.qspi_data_oe.value
        assert data_oe_val == 0xF
        await ClockCycles(dut.clk, 1, False)
        select_val = int(select.value) if hasattr(select.value, 'value') else select.value
        assert select_val == 0
        clk_out_val = int(dut.qspi_clk_out.value) if hasattr(dut.qspi_clk_out.value, 'value') else dut.qspi_clk_out.value
        assert clk_out_val == 0

    # Dummy
    if dut.qspi_flash_select == select:
        for i in range(2):
            await ClockCycles(dut.clk, 1, False)
            select_val = int(select.value) if hasattr(select.value, 'value') else select.value
            assert select_val == 0
            clk_out_val = int(dut.qspi_clk_out.value) if hasattr(dut.qspi_clk_out.value, 'value') else dut.qspi_clk_out.value
            assert clk_out_val == 1
            data_oe_val = int(dut.qspi_data_oe.value) if hasattr(dut.qspi_data_oe.value, 'value') else dut.qspi_data_oe.value
            assert data_oe_val == 0xF
            data_out_val = int(dut.qspi_data_out.value) if hasattr(dut.qspi_data_out.value, 'value') else dut.qspi_data_out.value
            assert data_out_val == 0xA
            await ClockCycles(dut.clk, 1, False)
            select_val = int(select.value) if hasattr(select.value, 'value') else select.value
            assert select_val == 0
            clk_out_val = int(dut.qspi_clk_out.value) if hasattr(dut.qspi_clk_out.value, 'value') else dut.qspi_clk_out.value
            assert clk_out_val == 0

    for i in range(4):
        await ClockCycles(dut.clk, 1, False)
        select_val = int(select.value) if hasattr(select.value, 'value') else select.value
        assert select_val == 0
        clk_out_val = int(dut.qspi_clk_out.value) if hasattr(dut.qspi_clk_out.value, 'value') else dut.qspi_clk_out.value
        assert clk_out_val == 1
        data_oe_val = int(dut.qspi_data_oe.value) if hasattr(dut.qspi_data_oe.value, 'value') else dut.qspi_data_oe.value
        assert data_oe_val == 0
        await ClockCycles(dut.clk, 1, False)
        select_val = int(select.value) if hasattr(select.value, 'value') else select.value
        assert select_val == 0
        clk_out_val = int(dut.qspi_clk_out.value) if hasattr(dut.qspi_clk_out.value, 'value') else dut.qspi_clk_out.value
        assert clk_out_val == 0


async def start_write(dut, addr):
    global select

    if addr >= 0x1800000:
        select = dut.qspi_ram_b_select
    else:
        select = dut.qspi_ram_a_select

    select_val = int(select.value) if hasattr(select.value, 'value') else select.value
    flash_sel_val = int(dut.qspi_flash_select.value) if hasattr(dut.qspi_flash_select.value, 'value') else dut.qspi_flash_select.value
    ram_a_sel_val = int(dut.qspi_ram_a_select.value) if hasattr(dut.qspi_ram_a_select.value, 'value') else dut.qspi_ram_a_select.value
    ram_b_sel_val = int(dut.qspi_ram_b_select.value) if hasattr(dut.qspi_ram_b_select.value, 'value') else dut.qspi_ram_b_select.value
    clk_out_val = int(dut.qspi_clk_out.value) if hasattr(dut.qspi_clk_out.value, 'value') else dut.qspi_clk_out.value
    data_oe_val = int(dut.qspi_data_oe.value) if hasattr(dut.qspi_data_oe.value, 'value') else dut.qspi_data_oe.value
    
    assert select_val == 0
    assert flash_sel_val == 1
    assert ram_a_sel_val == (0 if dut.qspi_ram_a_select == select else 1)
    assert ram_b_sel_val == (0 if dut.qspi_ram_b_select == select else 1)
    assert clk_out_val == 0
    assert data_oe_val == 0xF

    # Command
    cmd = 0x02
    for i in range(2):
        await ClockCycles(dut.clk, 1, False)
        select_val = int(select.value) if hasattr(select.value, 'value') else select.value
        assert select_val == 0
        clk_out_val = int(dut.qspi_clk_out.value) if hasattr(dut.qspi_clk_out.value, 'value') else dut.qspi_clk_out.value
        assert clk_out_val == 1
        data_out_val = int(dut.qspi_data_out.value) if hasattr(dut.qspi_data_out.value, 'value') else dut.qspi_data_out.value
        assert data_out_val == (cmd & 0xF0) >> 4
        data_oe_val = int(dut.qspi_data_oe.value) if hasattr(dut.qspi_data_oe.value, 'value') else dut.qspi_data_oe.value
        assert data_oe_val == 0xF
        cmd <<= 4
        await ClockCycles(dut.clk, 1, False)
        select_val = int(select.value) if hasattr(select.value, 'value') else select.value
        assert select_val == 0
        clk_out_val = int(dut.qspi_clk_out.value) if hasattr(dut.qspi_clk_out.value, 'value') else dut.qspi_clk_out.value
        assert clk_out_val == 0

    # Address
    for i in range(6):
        await ClockCycles(dut.clk, 1, False)
        select_val = int(select.value) if hasattr(select.value, 'value') else select.value
        assert select_val == 0
        clk_out_val = int(dut.qspi_clk_out.value) if hasattr(dut.qspi_clk_out.value, 'value') else dut.qspi_clk_out.value
        assert clk_out_val == 1
        data_out_val = int(dut.qspi_data_out.value) if hasattr(dut.qspi_data_out.value, 'value') else dut.qspi_data_out.value
        assert data_out_val == (addr >> (20 - i * 4)) & 0xF
        data_oe_val = int(dut.qspi_data_oe.value) if hasattr(dut.qspi_data_oe.value, 'value') else dut.qspi_data_oe.value
        assert data_oe_val == 0xF
        await ClockCycles(dut.clk, 1, False)
        select_val = int(select.value) if hasattr(select.value, 'value') else select.value
        assert select_val == 0
        clk_out_val = int(dut.qspi_clk_out.value) if hasattr(dut.qspi_clk_out.value, 'value') else dut.qspi_clk_out.value
        assert clk_out_val == 0


nibble_shift_order = [4, 0, 12, 8, 20, 16, 28, 24]

async def send_instr(dut, data, ok_to_exit=False, allow_long_delay=False):
    global pc
    #print(pc)

    flash_sel_val = int(dut.qspi_flash_select.value) if hasattr(dut.qspi_flash_select.value, 'value') else dut.qspi_flash_select.value
    
    if flash_sel_val == 1:
        for _ in range(10):
            await ClockCycles(dut.clk, 1, False)
            flash_sel_val = int(dut.qspi_flash_select.value) if hasattr(dut.qspi_flash_select.value, 'value') else dut.qspi_flash_select.value
            if flash_sel_val == 0:
                break
        await start_read(dut, pc)

    instr_len = 8 if (data & 3) == 3 else 4

    for i in range(instr_len):
        dut.qspi_data_in.value = (data >> (nibble_shift_order[i])) & 0xF
        await ClockCycles(dut.clk, 1, False)
        for _ in range(400 if allow_long_delay else 30):
            if ok_to_exit:
                flash_sel_val = int(dut.qspi_flash_select.value) if hasattr(dut.qspi_flash_select.value, 'value') else dut.qspi_flash_select.value
                if flash_sel_val == 1:
                    #print(" Early out")
                    return
            flash_sel_val = int(dut.qspi_flash_select.value) if hasattr(dut.qspi_flash_select.value, 'value') else dut.qspi_flash_select.value
            assert flash_sel_val == 0
            clk_out_val = int(dut.qspi_clk_out.value) if hasattr(dut.qspi_clk_out.value, 'value') else dut.qspi_clk_out.value
            if clk_out_val == 0:
                await ClockCycles(dut.clk, 1, False)
            else:
                break
        clk_out_val = int(dut.qspi_clk_out.value) if hasattr(dut.qspi_clk_out.value, 'value') else dut.qspi_clk_out.value
        assert clk_out_val == 1
        data_oe_val = int(dut.qspi_data_oe.value) if hasattr(dut.qspi_data_oe.value, 'value') else dut.qspi_data_oe.value
        assert data_oe_val == 0
        await ClockCycles(dut.clk, 1, False)
        clk_out_val = int(dut.qspi_clk_out.value) if hasattr(dut.qspi_clk_out.value, 'value') else dut.qspi_clk_out.value
        assert clk_out_val == 0
        if ok_to_exit:
            flash_sel_val = int(dut.qspi_flash_select.value) if hasattr(dut.qspi_flash_select.value, 'value') else dut.qspi_flash_select.value
            if flash_sel_val == 1:
                #print(" Early out")
                return
        if i != instr_len - 1:
            flash_sel_val = int(dut.qspi_flash_select.value) if hasattr(dut.qspi_flash_select.value, 'value') else dut.qspi_flash_select.value
            assert flash_sel_val == 0

    pc += instr_len >> 1

async def expect_load(dut, addr, val, bytes=4):
    if addr >= 0x1800000:
        select = dut.qspi_ram_b_select
    elif addr >= 0x1000000:
        select = dut.qspi_ram_a_select
    else:
        assert False # Load from flash not currently supported in this test

    for i in range(12):
        select_val = int(select.value) if hasattr(select.value, 'value') else select.value
        if select_val == 0:
            await start_read(dut, addr)
            dut.qspi_data_in.value = (val >> (nibble_shift_order[0])) & 0xF
            for j in range(1,bytes*2):
                await ClockCycles(dut.clk, 1, False)
                select_val = int(select.value) if hasattr(select.value, 'value') else select.value
                assert select_val == 0
                clk_out_val = int(dut.qspi_clk_out.value) if hasattr(dut.qspi_clk_out.value, 'value') else dut.qspi_clk_out.value
                assert clk_out_val == 1
                data_oe_val = int(dut.qspi_data_oe.value) if hasattr(dut.qspi_data_oe.value, 'value') else dut.qspi_data_oe.value
                assert data_oe_val == 0
                await ClockCycles(dut.clk, 1, False)
                clk_out_val = int(dut.qspi_clk_out.value) if hasattr(dut.qspi_clk_out.value, 'value') else dut.qspi_clk_out.value
                assert clk_out_val == 0
                dut.qspi_data_in.value = (val >> (nibble_shift_order[j])) & 0xF
            break
        else:
            flash_sel_val = int(dut.qspi_flash_select.value) if hasattr(dut.qspi_flash_select.value, 'value') else dut.qspi_flash_select.value
            if flash_sel_val == 0:
                await send_instr(dut, 0x0003, True)
            else:
                await ClockCycles(dut.clk, 1, False)
    else:
        assert False

async def load_reg(dut, reg, value):
    offset = random.randint(-0x400, 0x3FF)
    instr = InstructionLW(reg, gp, offset).encode()
    await send_instr(dut, instr)

    await expect_load(dut, 0x1000400 + offset, value)


send_nops = True
nop_task = None

async def nops_loop(dut):
    while send_nops:
        await send_instr(dut, InstructionADDI(x0, x0, 0).encode())

async def start_nops(dut):
    global send_nops, nop_task
    send_nops = True
    nop_task = cocotb.start_soon(nops_loop(dut))

    # This ensures that the nop task is actually started, so that it can be instantly stopped.
    await Timer(2, unit="ps")

async def stop_nops():
    global send_nops, nop_task
    send_nops = False
    if nop_task is not None:
        await nop_task
    nop_task = None

async def read_byte(dut, reg, expected_val):
  await send_instr(dut, InstructionSW(tp, reg, 0x18).encode())

  await start_nops(dut)
  for i in range(80):
      if dut.debug_uart_tx.value == 0:
          break
      else:
          await Timer(5, unit="ns")
  assert dut.debug_uart_tx.value == 0
  bit_time = 250
  await Timer(bit_time / 2, unit="ns")
  assert dut.debug_uart_tx.value == 0
  for i in range(8):
      await Timer(bit_time, unit="ns")
      assert dut.debug_uart_tx.value == (expected_val & 1)
      expected_val >>= 1
  await Timer(bit_time, unit="ns")
  assert dut.debug_uart_tx.value == 1

  await stop_nops()

async def expect_store(dut, addr, bytes=4, allow_long_delay=False):
    if addr >= 0x1800000:
        select = dut.qspi_ram_b_select
    elif addr >= 0x1000000:
        select = dut.qspi_ram_a_select
    else:
        assert False

    val = 0
    for i in range(12):
        select_val = int(select.value) if hasattr(select.value, 'value') else select.value
        if select_val == 0:
            await start_write(dut, addr)
            for j in range(bytes*2):
                await ClockCycles(dut.clk, 1, False)
                select_val = int(select.value) if hasattr(select.value, 'value') else select.value
                assert select_val == 0
                if j > 0 and (j % 8) == 0:
                    await ClockCycles(dut.clk, 1, False)
                    select_val = int(select.value) if hasattr(select.value, 'value') else select.value
                    assert select_val == 0
                    clk_out_val = int(dut.qspi_clk_out.value) if hasattr(dut.qspi_clk_out.value, 'value') else dut.qspi_clk_out.value
                    assert clk_out_val == 0
                    await ClockCycles(dut.clk, 1, False)
                clk_out_val = int(dut.qspi_clk_out.value) if hasattr(dut.qspi_clk_out.value, 'value') else dut.qspi_clk_out.value
                assert clk_out_val == 1
                data_oe_val = int(dut.qspi_data_oe.value) if hasattr(dut.qspi_data_oe.value, 'value') else dut.qspi_data_oe.value
                assert data_oe_val == 0xF
                data_out_val = int(dut.qspi_data_out.value) if hasattr(dut.qspi_data_out.value, 'value') else dut.qspi_data_out.value
                val |= data_out_val << (nibble_shift_order[j % 8])
                await ClockCycles(dut.clk, 1, False)
                select_val = int(select.value) if hasattr(select.value, 'value') else select.value
                assert select_val == (1 if j == bytes*2-1 else 0)
                clk_out_val = int(dut.qspi_clk_out.value) if hasattr(dut.qspi_clk_out.value, 'value') else dut.qspi_clk_out.value
                assert clk_out_val == 0
            await ClockCycles(dut.clk, 1, False)
            select_val = int(select.value) if hasattr(select.value, 'value') else select.value
            assert select_val == 1
            break
        else:
            flash_sel_val = int(dut.qspi_flash_select.value) if hasattr(dut.qspi_flash_select.value, 'value') else dut.qspi_flash_select.value
            if flash_sel_val == 0:
                await send_instr(dut, 0x0003, True, allow_long_delay)
            else:
                await ClockCycles(dut.clk, 1, False)
    else:
        assert False

    return val

async def read_reg(dut, reg, allow_long_delay=False):
    offset = random.randint(-0x400, 0x3FF)
    instr = InstructionSW(gp, reg, offset).encode()
    await send_instr(dut, instr)

    return await expect_store(dut, 0x1000400 + offset, 4, allow_long_delay)

async def set_all_outputs_to_peripheral(dut, peripheral_num):
    await send_instr(dut, InstructionADDI(a0, x0, 0xc0).encode())
    await send_instr(dut, InstructionSW(tp, a0, 0xc).encode())
    await send_instr(dut, InstructionADDI(a0, x0, peripheral_num).encode())
    for func_sel in range(0x60, 0x80, 4):
        await send_instr(dut, InstructionSW(tp, a0, func_sel).encode())

def set_pc(addr):
    global pc
    pc = addr
    #print("Jump to", addr)

def get_pc():
    global pc
    return pc
