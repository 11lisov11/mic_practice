"""Synthetic register tests; never connect to a board."""
from audit_uart_noise_readonly import decode, USART1, GPIOB, RCC, TIM1, DHCSR, READ_BLOCKS


def main():
    words = {USART1: 13 | (1 << 5) | (1 << 29), USART1 + 4: 0,
             USART1 + 8: 1, USART1 + 12: 1476, USART1 + 0x2C: 0,
             RCC + 8: 3 << 2, RCC + 12: 3 | (5 << 4) | (85 << 8), RCC + 0x88: 0,
             GPIOB: (2 << 12) | (2 << 14), GPIOB + 0x0C: (1 << 12) | (1 << 14),
             GPIOB + 0x20: (7 << 24) | (7 << 28), TIM1 + 0x44: 1 << 12, DHCSR: 0}
    assert decode(words)["pass"]
    assert abs(decode(words)["nominal_baud"] - 115176.1517615) < .001
    mutations = ((USART1, 1 << 15), (USART1 + 8, 1 << 11), (USART1 + 4, 1 << 12),
                 (USART1, 1 << 10), (USART1, 1 << 29), (USART1, 1 << 5),
                 (USART1 + 8, 1), (USART1 + 8, 1 << 9), (TIM1 + 0x44, 1 << 15),
                 (TIM1 + 0x44, 1 << 12), (DHCSR, 1 << 17),
                 (GPIOB + 0x20, 1 << 24), (GPIOB + 0x0C, 1 << 12), (GPIOB, 1 << 12),
                 (RCC + 8, 1 << 11), (RCC + 12, 1), (USART1 + 0x2C, 1))
    for address, bit in mutations:
        changed = dict(words)
        changed[address] ^= bit
        assert not decode(changed)["pass"], (hex(address), hex(bit))
    for brr in (0, 100, 2000):
        changed = dict(words)
        changed[USART1 + 12] = brr
        assert not decode(changed)["pass"]
    # No consume-on-read data registers in any block.
    assert all(not (address <= USART1 + 0x24 < address + size) for address, size in READ_BLOCKS)
    print({"pass": True, "cases": 22, "hardware_access": False})


if __name__ == "__main__":
    main()
