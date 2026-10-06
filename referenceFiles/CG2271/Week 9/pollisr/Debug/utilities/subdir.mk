################################################################################
# Automatically-generated file. Do not edit!
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
C_SRCS += \
../utilities/fsl_assert.c 

C_DEPS += \
./utilities/fsl_assert.d 

OBJS += \
./utilities/fsl_assert.o 


# Each subdirectory must supply rules for building sources it contributes
utilities/%.o: ../utilities/%.c utilities/subdir.mk
	@echo 'Building file: $<'
	@echo 'Invoking: MCU C Compiler'
	arm-none-eabi-gcc -D__REDLIB__ -DCPU_MCXC444VLH -DCPU_MCXC444VLH_cm0plus -DSDK_DEBUGCONSOLE=1 -DCR_INTEGER_PRINTF -DPRINTF_FLOAT_ENABLE=0 -DSDK_DEBUGCONSOLE_UART -DSERIAL_PORT_TYPE_UART=1 -DSDK_OS_FREE_RTOS -D__MCUXPRESSO -D__USE_CMSIS -DDEBUG -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Week 9\pollisr\board" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Week 9\pollisr\source" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Week 9\pollisr\drivers" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Week 9\pollisr\CMSIS" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Week 9\pollisr\CMSIS\m-profile" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Week 9\pollisr\utilities" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Week 9\pollisr\utilities\debug_console\config" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Week 9\pollisr\device" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Week 9\pollisr\device\periph2" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Week 9\pollisr\utilities\debug_console" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Week 9\pollisr\component\serial_manager" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Week 9\pollisr\component\lists" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Week 9\pollisr\utilities\str" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Week 9\pollisr\component\uart" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Week 9\pollisr\freertos\freertos-kernel\include" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Week 9\pollisr\freertos\freertos-kernel\portable\GCC\ARM_CM0" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Week 9\pollisr\freertos\freertos-kernel\template" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Week 9\pollisr\freertos\freertos-kernel\template\ARM_CM0" -O0 -fno-common -g3 -gdwarf-4 -Wall -c -ffunction-sections -fdata-sections -fno-builtin -fmerge-constants -fmacro-prefix-map="$(<D)/"= -mcpu=cortex-m0plus -mthumb -D__REDLIB__ -fstack-usage -specs=redlib.specs -MMD -MP -MF"$(@:%.o=%.d)" -MT"$(@:%.o=%.o)" -MT"$(@:%.o=%.d)" -o "$@" "$<"
	@echo 'Finished building: $<'
	@echo ' '


clean: clean-utilities

clean-utilities:
	-$(RM) ./utilities/fsl_assert.d ./utilities/fsl_assert.o

.PHONY: clean-utilities

