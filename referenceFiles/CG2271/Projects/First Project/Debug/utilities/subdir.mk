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
	arm-none-eabi-gcc -D__REDLIB__ -DCPU_MCXC444VLH -DCPU_MCXC444VLH_cm0plus -DSERIAL_PORT_TYPE_UART=1 -DSDK_DEBUGCONSOLE=1 -DCR_INTEGER_PRINTF -DPRINTF_FLOAT_ENABLE=0 -DSDK_DEBUGCONSOLE_UART -D__MCUXPRESSO -D__USE_CMSIS -DDEBUG -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Projects\First Project\board" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Projects\First Project\source" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Projects\First Project\drivers" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Projects\First Project\CMSIS" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Projects\First Project\CMSIS\m-profile" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Projects\First Project\utilities" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Projects\First Project\utilities\debug_console\config" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Projects\First Project\device" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Projects\First Project\device\periph2" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Projects\First Project\utilities\debug_console" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Projects\First Project\component\serial_manager" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Projects\First Project\component\lists" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Projects\First Project\utilities\str" -I"C:\Users\famil\OneDrive\Documents\School\Sem 5\CG2271\Projects\First Project\component\uart" -O0 -fno-common -g3 -gdwarf-4 -Wall -c -ffunction-sections -fdata-sections -fno-builtin -fmerge-constants -fmacro-prefix-map="$(<D)/"= -mcpu=cortex-m0plus -mthumb -D__REDLIB__ -fstack-usage -specs=redlib.specs -MMD -MP -MF"$(@:%.o=%.d)" -MT"$(@:%.o=%.o)" -MT"$(@:%.o=%.d)" -o "$@" "$<"
	@echo 'Finished building: $<'
	@echo ' '


clean: clean-utilities

clean-utilities:
	-$(RM) ./utilities/fsl_assert.d ./utilities/fsl_assert.o

.PHONY: clean-utilities

