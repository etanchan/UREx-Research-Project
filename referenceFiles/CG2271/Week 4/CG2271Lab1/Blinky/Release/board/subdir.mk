################################################################################
# Automatically-generated file. Do not edit!
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../board/board.c \
../board/clock_config.c \
../board/peripherals.c \
../board/pin_mux.c 

C_DEPS += \
./board/board.d \
./board/clock_config.d \
./board/peripherals.d \
./board/pin_mux.d 

OBJS += \
./board/board.o \
./board/clock_config.o \
./board/peripherals.o \
./board/pin_mux.o 


# Each subdirectory must supply rules for building sources it contributes
board/%.o: ../board/%.c board/subdir.mk
	@echo 'Building file: $<'
	@echo 'Invoking: MCU C Compiler'
	arm-none-eabi-gcc -DCPU_MCXC444VLH -DCPU_MCXC444VLH_cm0plus -DSDK_DEBUGCONSOLE=1 -DCR_INTEGER_PRINTF -DPRINTF_FLOAT_ENABLE=0 -DSDK_DEBUGCONSOLE_UART -DSERIAL_PORT_TYPE_UART=1 -D__MCUXPRESSO -D__USE_CMSIS -DNDEBUG -D__REDLIB__ -I"/Users/ctank/Documents/MCUXpressoIDE_24.12.148/workspace/Blinky/board" -I"/Users/ctank/Documents/MCUXpressoIDE_24.12.148/workspace/Blinky/source" -I"/Users/ctank/Documents/MCUXpressoIDE_24.12.148/workspace/Blinky/drivers" -I"/Users/ctank/Documents/MCUXpressoIDE_24.12.148/workspace/Blinky/CMSIS" -I"/Users/ctank/Documents/MCUXpressoIDE_24.12.148/workspace/Blinky/CMSIS/m-profile" -I"/Users/ctank/Documents/MCUXpressoIDE_24.12.148/workspace/Blinky/utilities" -I"/Users/ctank/Documents/MCUXpressoIDE_24.12.148/workspace/Blinky/utilities/debug_console/config" -I"/Users/ctank/Documents/MCUXpressoIDE_24.12.148/workspace/Blinky/device" -I"/Users/ctank/Documents/MCUXpressoIDE_24.12.148/workspace/Blinky/device/periph2" -I"/Users/ctank/Documents/MCUXpressoIDE_24.12.148/workspace/Blinky/utilities/debug_console" -I"/Users/ctank/Documents/MCUXpressoIDE_24.12.148/workspace/Blinky/component/serial_manager" -I"/Users/ctank/Documents/MCUXpressoIDE_24.12.148/workspace/Blinky/component/lists" -I"/Users/ctank/Documents/MCUXpressoIDE_24.12.148/workspace/Blinky/utilities/str" -I"/Users/ctank/Documents/MCUXpressoIDE_24.12.148/workspace/Blinky/component/uart" -Os -fno-common -g -gdwarf-4 -Wall -c -ffunction-sections -fdata-sections -fno-builtin -fmacro-prefix-map="$(<D)/"= -mcpu=cortex-m0plus -mthumb -D__REDLIB__ -fstack-usage -specs=redlib.specs -MMD -MP -MF"$(@:%.o=%.d)" -MT"$(@:%.o=%.o)" -MT"$(@:%.o=%.d)" -o "$@" "$<"
	@echo 'Finished building: $<'
	@echo ' '


clean: clean-board

clean-board:
	-$(RM) ./board/board.d ./board/board.o ./board/clock_config.d ./board/clock_config.o ./board/peripherals.d ./board/peripherals.o ./board/pin_mux.d ./board/pin_mux.o

.PHONY: clean-board

