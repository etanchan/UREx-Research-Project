/*
 * Copyright 2016-2025 NXP
 * All rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

/**
 * @file    Blinky.c
 * @brief   Application entry point.
 */
#include <stdio.h>
#include "board.h"
#include "peripherals.h"
#include "pin_mux.h"
#include "clock_config.h"
#include "fsl_debug_console.h"
/* TODO: insert other include files here. */

/* TODO: insert other definitions and declarations here. */

// LED pin numbers
#define RED_PIN		31	// PTE31

#define DELAY	0x100000

/* Delay Function */
static void delay(volatile uint32_t nof) {
	while(nof!=0) {
	__asm("NOP");
	nof--;
	}
}

/*
Usage Example:
delay(0x80000);
*/

void initGPIO() {

	SIM->SCGC5 |= SIM_SCGC5_PORTE_MASK;

	PORTE->PCR[RED_PIN] &= ~PORT_PCR_MUX_MASK;

	PORTE->PCR[RED_PIN] = PORT_PCR_MUX(1);
	GPIOE->PDDR |= (1 << RED_PIN);

}


void ledOn() {
	GPIOE->PCOR |= (1 << RED_PIN);
}

void ledOff() {
	GPIOE->PSOR |= (1 << RED_PIN);
}

/*
 * @brief   Application entry point.
 */
int main(void) {

    /* Init board hardware. */
    BOARD_InitBootPins();
    BOARD_InitBootClocks();
    BOARD_InitBootPeripherals();
#ifndef BOARD_INIT_DEBUG_CONSOLE_PERIPHERAL
    /* Init FSL debug console. */
    BOARD_InitDebugConsole();
#endif


    /* Force the counter to be placed into memory. */
    /* Enter an infinite loop, just incrementing a counter. */
    initGPIO();
    ledOff();

    while(1) {
    	PRINTF("HELLO WORLD!\r\n");
    	ledOn();
    	delay(DELAY);
    	ledOff();
    	delay(DELAY);
    }
    return 0 ;
}
