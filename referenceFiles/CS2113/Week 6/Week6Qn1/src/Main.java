import java.util.ArrayList;

public class Main {
    static ArrayList<Integer> list = new ArrayList<>();

    public static void addNumber(int number) {
        list.add(number);
        System.out.println(list.toString());
    }

    public static int getTotal() {
        int total = 0;
        for (int i : list) {
            total += i;
        }
        return total;
    }

    public static boolean isFound(int number) {
        return list.contains(number);
    }

    public static void removeNumber(int number) {
        list.remove(Integer.valueOf(number));
        System.out.println(list.toString());

    }

    public static void main(String[] args) {


        System.out.println("Adding numbers to the list");
        addNumber(3);
        addNumber(8);
        addNumber(24);
        System.out.println("The total is: " + getTotal());
        System.out.println("8 in the list : " + isFound(8));
        System.out.println("5 in the list : " + isFound(5));
        removeNumber(8);
        System.out.println("The total is: " + getTotal());
    }

}