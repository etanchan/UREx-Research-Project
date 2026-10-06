import java.util.HashMap;

public class Main {
    private static HashMap<String, Integer> roster = new HashMap<>();

    public static void addToRoster(String day) {
        if (roster.containsKey(day)) {
            roster.put(day, roster.get(day) + 1);
        } else {
            roster.put(day, 1);
        }
    }

    public static void printRoster() {
        for (HashMap.Entry<String, Integer> entry : roster.entrySet()) {
            System.out.println(entry.getKey() + " => " + entry.getValue());
        }
    }


    public static void main(String[] args) {
        addToRoster("Monday"); // i.e., one person signed up for Monday
        addToRoster("Wednesday"); // i.e., one person signed up for Wednesday
        addToRoster("Wednesday"); // i.e., another person signed up for Wednesday
        addToRoster("Friday");
        addToRoster("Monday");
        printRoster();
    }

}
