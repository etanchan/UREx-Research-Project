public class Main {

    public static void describe(String colour, Priority p) {
        switch (p) {
        case LOW:
            System.out.println(colour + " indicates low priority");
            break;
        case MEDIUM:
            System.out.println(colour + " indicates medium priority");
            break;
        case HIGH:
            System.out.println(colour + " indicates high priority");
        }
    }

    public static void main(String[] args) {
        describe("Red", Priority.HIGH);
        describe("Orange", Priority.MEDIUM);
        describe("Blue", Priority.MEDIUM);
        describe("Green", Priority.LOW);
    }
}